# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('registrasion', '0006_category_required'),
    ]

    operations = [
        migrations.AddField(
            model_name='category',
            name='limit_per_user',
            field=models.PositiveIntegerField(null=True, verbose_name='Limit per user', blank=True),
        ),
        migrations.AlterField(
            model_name='product',
            name='limit_per_user',
            field=models.PositiveIntegerField(null=True, verbose_name='Limit per user', blank=True),
        ),
    ]
