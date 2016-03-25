# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('registrasion', '0004_auto_20160323_2137'),
    ]

    operations = [
        migrations.RenameField(
            model_name='badgeandprofile',
            old_name='profile',
            new_name='attendee',
        ),
    ]
