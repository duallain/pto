# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from django.contrib.auth.models import User


class EmailOrUsernameModelBackend(object):

    supports_object_permissions = False
    supports_anonymous_user = False
    supports_inactive_user = False

    def authenticate(self, username=None, password=None):
        if '@' in username:
            kwargs = {'email__iexact': username}
        else:
            kwargs = {'username': username}
        try:
            user = User.objects.get(**kwargs)
            # Strangely, if user.password is '', user.has_usable_password()
            # will return True and trying to use user.check_password()
            # against an empty password will fail with a ValueError  :(
            if user.password and user.check_password(password):
                return user
        except User.DoesNotExist:
            return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:  # pragma: no cover
            return None
