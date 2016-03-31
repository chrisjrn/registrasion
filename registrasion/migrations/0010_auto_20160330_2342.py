# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('registrasion', '0009_auto_20160330_2336'),
    ]

    operations = [
        migrations.AlterField(
            model_name='timeorstocklimitenablingcondition',
            name='end_time',
            field=models.DateTimeField(help_text='Products included in this condition will only be available before this time.', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='timeorstocklimitenablingcondition',
            name='limit',
            field=models.PositiveIntegerField(help_text='The number of items under this grouping that can be purchased.', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='timeorstocklimitenablingcondition',
            name='start_time',
            field=models.DateTimeField(help_text='Products included in this condition will only be available after this time.', null=True, blank=True),
        ),
    ]
