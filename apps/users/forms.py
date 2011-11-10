# ***** BEGIN LICENSE BLOCK *****
# Version: MPL 1.1/GPL 2.0/LGPL 2.1
#
# The contents of this file are subject to the Mozilla Public License Version
# 1.1 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License
# for the specific language governing rights and limitations under the
# License.
#
# The Original Code is Mozilla Sheriff Duty.
#
# The Initial Developer of the Original Code is Mozilla Corporation.
# Portions created by the Initial Developer are Copyright (C) 2011
# the Initial Developer. All Rights Reserved.
#
# Contributor(s):
#
# Alternatively, the contents of this file may be used under the terms of
# either the GNU General Public License Version 2 or later (the "GPL"), or
# the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
# in which case the provisions of the GPL or the LGPL are applicable instead
# of those above. If you wish to allow use of your version of this file only
# under the terms of either the GPL or the LGPL, and not to allow others to
# use your version of this file under the terms of the MPL, indicate your
# decision by deleting the provisions above and replace them with the notice
# and other provisions required by the GPL or the LGPL. If you do not delete
# the provisions above, a recipient may use your version of this file under
# the terms of any one of the MPL, the GPL or the LGPL.
#
# ***** END LICENSE BLOCK *****

import datetime
from django import forms
from django.contrib.auth.models import User
import django.contrib.auth.forms
from .models import UserProfile
from dates.forms import BaseModelForm


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
    class Meta:
        model = UserProfile
        fields = ('start_date', 'country', 'city')

    def clean_start_date(self):
        value = self.cleaned_data['start_date']
        if value > datetime.date.today():
            raise forms.ValidationError("Can't be in future")
        return value

    def clean_country(self):
        value = self.cleaned_data['country']
        # XXX: we ought to massage and validate this value
        # so that for example 'United Kingdom' -> 'GB'
        return value
