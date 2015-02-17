# -*- coding: utf-8 -*-
import logging
LOG = logging.getLogger(__name__)

import uuid
import csv
from datetime import datetime

from django.shortcuts import render
from django.views.generic import DetailView, ListView, FormView
from django.views.generic.detail import SingleObjectMixin
from django.http import HttpResponse, Http404
from django.contrib.gis.geos import Point
from django.db import transaction

from braces.views import JSONResponseMixin, LoginRequiredMixin

from .models import Locality, Domain, Changeset
from .utils import render_fragment, parse_bbox
from .forms import LocalityForm, DomainForm

from .map_clustering import cluster

import overpass


class LocalitiesLayer(JSONResponseMixin, ListView):
    """
    Returns JSON representation of clustered points for the current map view

    Map view is defined by a *bbox*, *zoom* and *iconsize*
    """

    def _parse_request_params(self, request):
        """
        Try to parse arguments for a request and any error during parsing will
        raise Http404 exception
        """

        if not(all(param in request.GET for param in [
                'bbox', 'zoom', 'iconsize'])):
            raise Http404

        try:
            bbox_poly = parse_bbox(request.GET.get('bbox'))
            zoom = int(request.GET.get('zoom'))
            icon_size = map(int, request.GET.get('iconsize').split(','))

        except:
            # return 404 if any of parameters are missing or not parsable
            raise Http404

        if zoom < 0 or zoom > 20:
            # zoom should be between 0 and 20
            raise Http404
        if any((size < 0 for size in icon_size)):
            # icon sizes should be positive
            raise Http404

        return (bbox_poly, zoom, icon_size)

    def get(self, request, *args, **kwargs):
        # parse request params
        bbox, zoom, iconsize = self._parse_request_params(request)

        # cluster Localites for a view
        object_list = cluster(Locality.objects.in_bbox(bbox), zoom, *iconsize)

        return self.render_json_response(object_list)


class LocalityInfo(JSONResponseMixin, DetailView):
    """
    Returns JSON representation of an Locality object (repr_dict) and a
    rendered template fragment (repr)
    """

    model = Locality
    slug_field = 'uuid'
    slug_url_kwarg = 'uuid'

    def get_queryset(self):
        queryset = (
            Locality.objects.select_related('domain')
        )
        return queryset

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        obj_repr = self.object.repr_dict()
        data_repr = render_fragment(
            self.object.domain.template_fragment, obj_repr
        )
        obj_repr.update({'repr': data_repr})

        return self.render_json_response(obj_repr)


class LocalityUpdate(LoginRequiredMixin, SingleObjectMixin, FormView):
    """
    Handles Locality updates, users need to be logged in order to update a
    Locality
    """

    raise_exception = True
    form_class = LocalityForm
    template_name = 'updateform.html'
    slug_field = 'uuid'
    slug_url_kwarg = 'uuid'

    def get_queryset(self):
        queryset = (
            Locality.objects.select_related('domain')
        )
        return queryset

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super(LocalityUpdate, self).get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super(LocalityUpdate, self).post(request, *args, **kwargs)

    def form_valid(self, form):
        # update everything in one transaction
        with transaction.atomic():
            self.object.set_geom(
                form.cleaned_data.pop('lon'),
                form.cleaned_data.pop('lat')
            )
            if self.object.tracker.changed():
                # there are some changes so create a new changeset
                tmp_changeset = Changeset.objects.create(
                    social_user=self.request.user
                )
                self.object.changeset = tmp_changeset
            self.object.save()
            self.object.set_values(
                form.cleaned_data, social_user=self.request.user
            )

            return HttpResponse('OK')

        # transaction failed
        return HttpResponse('ERROR updating Locality and values')

    def get_form(self, form_class):
        return form_class(locality=self.object, **self.get_form_kwargs())


class LocalityCreate(LoginRequiredMixin, SingleObjectMixin, FormView):
    """
    Handles Locality creates, users need to be logged in order to create a
    Locality
    """

    raise_exception = True
    form_class = DomainForm
    template_name = 'updateform.html'

    def get_queryset(self):
        queryset = Domain.objects
        return queryset

    def get_object(self, queryset=None):
        if queryset is None:
            queryset = self.get_queryset()
        queryset = queryset.filter(name=self.kwargs.get('domain'))

        obj = queryset.get()
        return obj

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super(LocalityCreate, self).get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super(LocalityCreate, self).post(request, *args, **kwargs)

    def form_valid(self, form):
        # create new as a single transaction
        with transaction.atomic():
            tmp_changeset = Changeset.objects.create(
                social_user=self.request.user
            )

            # generate new uuid
            tmp_uuid = uuid.uuid4().hex

            loc = Locality()
            loc.changeset = tmp_changeset
            loc.domain = self.object
            loc.uuid = tmp_uuid

            # generate unique upstream_id
            loc.upstream_id = u'web¶{}'.format(tmp_uuid)

            loc.geom = Point(
                form.cleaned_data.pop('lon'), form.cleaned_data.pop('lat')
            )
            loc.save()
            loc.set_values(form.cleaned_data, social_user=self.request.user)

            return HttpResponse(loc.pk)
        # transaction failed
        return HttpResponse('ERROR creating Locality and values')

    def get_form(self, form_class):
        return form_class(domain=self.object, **self.get_form_kwargs())


def build_overpass_ql(bounding_box, key_values):
    """Build a overpass query language based on the arguments

    :param bounding_box: A list that contains South, West, North, East
    :type bounding_box: list

    :param key_values: A dictionary of key and value. Key represent a key in
        osm and value represent the possible value that the user wants
    :type key_values: dict

    :returns: An overpass query language
    :rtype: str
    """
    bounding_box_ql = ','.join([str(x) for x in bounding_box])
    bounding_box_ql = '(' + bounding_box_ql + ')'

    key_values_ql = ''
    for key, values in key_values.iteritems():
        key_ql = '"' + key + '"'
        values_ql = '"' + '|'.join(values) + '"'

        # Use ~ for not exact, = for exact value
        key_value_ql = '[' + key_ql + '~' + values_ql + ']'
        key_values_ql += key_value_ql

    overpass_ql = 'node' + key_values_ql + bounding_box_ql + ';out;'

    return overpass_ql


def parse_overpass_result(dictionary_result):
    """Parse result from overpass.

    :param dictionary_result: A dictionary that contains the result.
    :type dictionary_result: dict

    :returns: A list of nodes, each element contains id, lon, lat, amenity,
            and name
    :rtype: list
    """
    result = []

    elements = dictionary_result['elements']
    for element in elements:
        node = {}
        latitude = element['lat']
        longitude = element['lon']
        node_id = element['id']
        node['latitude'] = latitude
        node['longitude'] = longitude
        node['id'] = node_id
        tags = element['tags']
        for key, value in tags.iteritems():
            node[key] = value

        result.append(node)
    return result


def list_of_dict_to_csv(list_of_dict, filename=''):
    """Create a csv file from list of dict.

    Assuming that all have the same dictionary keys.
    :param list_of_dict: List of uniform dictionary
    :type list_of_dict: list

    :param filename: Filename for the csv file. If empty uses current_time.csv.
    :type filename: str

    :returns: A path to csv file
    :rtype: str
    """
    if not filename:
        filename = datetime.now().strftime('%Y%m%d_%H%M%S') + '.csv'
    keys = []
    for dictionary in list_of_dict:
        list_key = dictionary.keys()
        for key in list_key:
            if key not in keys:
                keys.append(key)

    output_file = open(filename, 'wb')
    writer = csv.DictWriter(output_file, keys)
    writer.writeheader()
    for row in list_of_dict:
        writer.writerow(
            dict((k, v.encode('utf-8') if type(v) is unicode else v)
                 for k, v in row.iteritems()))
    output_file.close()

    return filename


def importer(request):
    context = {}
    try:
        boundary = {
            'north': request.GET['north'],
            'east': request.GET['east'],
            'south': request.GET['south'],
            'west': request.GET['west'],
            }
        context['boundary'] = boundary
        context['flag_boundary'] = True

    except KeyError:
        context['flag_boundary'] = False
        return render(request, 'importer.html', context)

    # Use overpass
    api = overpass.API()
    key_values = {
        'amenity': [
            'hospital',
            'clinic',
            'community_centre',
            'social_centre',
            'pharmacy',
            'social_facility',
            'nursing_home',
            'doctors',
            'dentist'
        ]
    }
    bounding_box = [
        boundary['south'],
        boundary['west'],
        boundary['north'],
        boundary['east'],
    ]
    overpass_ql = build_overpass_ql(bounding_box, key_values)
    context['overpass_ql'] = overpass_ql
    response = api.Get(overpass_ql)
    good_result = parse_overpass_result(response)

    filename = list_of_dict_to_csv(good_result)
    context['filename'] = filename

    return render(request, 'importer.html', context)
