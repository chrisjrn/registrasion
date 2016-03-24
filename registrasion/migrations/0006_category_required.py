# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('registrasion', '0005_auto_20160323_2141'),
    ]

    operations = [
        migrations.AddField(
            model_name='category',
            name='required',
            field=models.BooleanField(default=False),
            preserve_default=False,
        ),
    ]
