# -*- coding: utf-8 -*-
import logging
from datetime import datetime
LOG = logging.getLogger(__name__)

import django.forms as forms
from django.utils.safestring import mark_safe

from .models import Domain
from .utils import render_fragment


class DomainModelForm(forms.ModelForm):
    """
    Used in django admin

    Special validation rules for template_fragment field
    """

    class Meta:
        model = Domain
        fields = ('name', 'description', 'template_fragment')

    def clean_template_fragment(self):
        try:
            render_fragment(self.cleaned_data['template_fragment'], {})
        except Exception, e:
            raise forms.ValidationError(
                'Template Syntax Error: {}'.format(e.message)
            )

        return self.cleaned_data['template_fragment']


class DomainForm(forms.Form):
    """
    Used when creating a new Locality

    Form will dynamically add every specification of an attribute as a simple
    CharField
    """

    lon = forms.FloatField()
    lat = forms.FloatField()

    def __init__(self, *args, **kwargs):
        # pop arguments which are not form fields
        domain = kwargs.pop('domain')

        super(DomainForm, self).__init__(*args, **kwargs)

        # populate form with attribute specifications
        for spec in domain.specification_set.select_related('attribute'):
            field = forms.CharField(
                label=spec.attribute.key, required=spec.required
            )
            self.fields[spec.attribute.key] = field


class LocalityForm(forms.Form):
    """
    Used when updating a Locality

    Form will dynamically add every specification of an attribute as a simple
    CharField, and prefill it with initial values
    """

    lon = forms.FloatField()
    lat = forms.FloatField()

    def __init__(self, *args, **kwargs):
        # pop arguments which are not form fields
        locality = kwargs.pop('locality')

        tmp_initial_data = {
            'lon': locality.geom.x, 'lat': locality.geom.y
        }

        # Locality forms are special as they automatically collect initial data
        # based on the actual models
        for value in locality.value_set.select_related('specification').all():
            tmp_initial_data.update({
                value.specification.attribute.key: value.data
            })

        # set initial form data
        kwargs.update({'initial': tmp_initial_data})

        super(LocalityForm, self).__init__(*args, **kwargs)

        for spec in (
                locality.domain.specification_set.select_related('attribute')):

            field = forms.CharField(
                label=spec.attribute.key, required=spec.required
            )
            self.fields[spec.attribute.key] = field
            self.fields[spec.attribute.key].widget.attrs.update(
                {'class': 'form-control'})


def json_file_name(instance, filename):
    return '/'.join(['json', datetime.now().strftime('%Y%m'), filename])

def csv_file_name(instance, filename):
    return '/'.join(['csv', datetime.now().strftime('%Y%m'), filename])

class HorizontalRadioRenderer(forms.RadioSelect.renderer):
    def render(self):
        return mark_safe(u'\n'.join([u'%s\n' % w for w in self]))

class DataLoaderForm(forms.Form):
    """Used when loading data."""

    REPLACE_DATA_CODE = 1
    UPDATE_DATA_CODE = 2

    DATA_LOADER_MODE_CHOICES = (
        (REPLACE_DATA_CODE, 'Replace Data'),
        (UPDATE_DATA_CODE, 'Update Data')
    )

    organization_name = forms.CharField(
        label="Organization's name",
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Name of the organization.'
            }
        )
    )
    json_concept_mapping = forms.FileField(
        label='JSON Concept Mapping',
        # upload_to=json_file_name,
        widget=forms.ClearableFileInput(
            attrs={'class': 'form-control'}
        )
    )
    csv_data = forms.FileField(
        label='CSV Data',
        # upload_to=csv_file_name,
        widget=forms.ClearableFileInput(
            attrs={'class': 'form-control'}
        )
    )
    data_loader_mode = forms.ChoiceField(
        label='Data Loader Mode',
        choices=DATA_LOADER_MODE_CHOICES,
        initial=REPLACE_DATA_CODE,
        widget=forms.RadioSelect(
            renderer=HorizontalRadioRenderer,
            attrs={'class': 'form-control'}
        )
    )
