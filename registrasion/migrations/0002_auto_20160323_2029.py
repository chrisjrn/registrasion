# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('registrasion', '0001_squashed_0002_auto_20160304_1723'),
    ]

    operations = [
        migrations.AddField(
            model_name='badge',
            name='accessibility_requirements',
            field=models.CharField(max_length=256, blank=True),
        ),
        migrations.AddField(
            model_name='badge',
            name='dietary_requirements',
            field=models.CharField(max_length=256, blank=True),
        ),
        migrations.AddField(
            model_name='badge',
            name='free_text_1',
            field=models.CharField(help_text="A line of free text that will appear on your badge. Use this for your Twitter handle, IRC nick, your preferred pronouns or anything else you'd like people to see on your badge.", max_length=64, verbose_name='Free text line 1', blank=True),
        ),
        migrations.AddField(
            model_name='badge',
            name='free_text_2',
            field=models.CharField(max_length=64, verbose_name='Free text line 2', blank=True),
        ),
        migrations.AddField(
            model_name='badge',
            name='gender',
            field=models.CharField(max_length=64, blank=True),
        ),
        migrations.AddField(
            model_name='badge',
            name='of_legal_age',
            field=models.BooleanField(default=False, verbose_name='18+?'),
        ),
        migrations.AlterField(
            model_name='badge',
            name='company',
            field=models.CharField(help_text="The name of your company, as you'd like it on your badge", max_length=64, blank=True),
        ),
        migrations.AlterField(
            model_name='badge',
            name='name',
            field=models.CharField(help_text="Your name, as you'd like it on your badge", max_length=64),
        ),
    ]
