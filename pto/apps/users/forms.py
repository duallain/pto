# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from django import forms
import django.contrib.auth.forms
from .models import UserProfile
from apps.dates.forms import BaseModelForm
from lib.country_aliases import ALIASES as COUNTRY_ALIASES


class EmailInput(forms.widgets.Input):
    input_type = 'email'

    def render(self, name, value, attrs=None):
        if attrs is None:
            attrs = {}
        attrs.update(dict(autocorrect='off',
                          autocapitalize='off',
                          spellcheck='false'))
        return super(EmailInput, self).render(name, value, attrs=attrs)


class AuthenticationForm(django.contrib.auth.forms.AuthenticationForm):
    """override the authentication form because we use the email address as the
    key to authentication."""
    # allows for using email to log in
    username = forms.CharField(label="Username", max_length=75,
                               widget=EmailInput())
    #rememberme = forms.BooleanField(label="Remember me", required=False)


class ProfileForm(BaseModelForm):
    country = forms.ChoiceField(widget=forms.widgets.Select())

    class Meta:
        model = UserProfile
        fields = ('city',)

    def __init__(self, *args, **kwargs):
        super(ProfileForm, self).__init__(*args, **kwargs)

        country_choices = []
        _all_longforms = []
        for each in (UserProfile.objects.exclude(country='')
                     .values('country')
                     .distinct()
                     .order_by('country')):
            country = each['country']
            long_form = country
            if long_form in COUNTRY_ALIASES.values():
                long_form = [k for (k, v) in COUNTRY_ALIASES.items()
                             if v == country][0]
            _all_longforms.append(long_form)
            country_choices.append((country, long_form))
        for alias, country in COUNTRY_ALIASES.items():
            if alias not in _all_longforms:
                _all_longforms.append(alias)
                country_choices.append((country, alias))

        country_choices.sort(lambda x, y: cmp(x[1], y[1]))
        self.fields['country'].choices = country_choices

    def clean_country(self):  # pragma: no cover
        # this method doesn't do much since we're using a ChoiceField
        value = self.cleaned_data['country']
        if value in COUNTRY_ALIASES.values():
            pass
        elif value in COUNTRY_ALIASES:
            value = COUNTRY_ALIASES.get(value)
        else:
            # search case-insensitively
            for alias in COUNTRY_ALIASES:
                if alias.lower() == value.lower():
                    value = COUNTRY_ALIASES[alias]
                    break
        return value
