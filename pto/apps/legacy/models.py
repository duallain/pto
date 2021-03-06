# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

# This is a Django model created based on the old PTO app which was just one
# table in the PHP code.

from django.db import models


class Pto(models.Model):
    id = models.IntegerField(primary_key=True)
    person = models.CharField(max_length=384)
    added = models.IntegerField()
    hours = models.FloatField()
    hours_daily = models.TextField()
    details = models.CharField(max_length=765)
    start = models.IntegerField()
    end = models.IntegerField()
    class Meta:
        db_table = u'pto'
