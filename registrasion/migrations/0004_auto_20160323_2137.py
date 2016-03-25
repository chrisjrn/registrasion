# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('registrasion', '0003_auto_20160323_2044'),
    ]

    operations = [
        migrations.CreateModel(
            name='Attendee',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('completed_registration', models.BooleanField(default=False)),
                ('highest_complete_category', models.IntegerField(default=0)),
                ('user', models.OneToOneField(to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='BadgeAndProfile',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(help_text="Your name, as you'd like it to appear on your badge. ", max_length=64, verbose_name='Your name (for your conference nametag)')),
                ('company', models.CharField(help_text="The name of your company, as you'd like it on your badge", max_length=64, blank=True)),
                ('free_text_1', models.CharField(help_text="A line of free text that will appear on your badge. Use this for your Twitter handle, IRC nick, your preferred pronouns or anything else you'd like people to see on your badge.", max_length=64, verbose_name='Free text line 1', blank=True)),
                ('free_text_2', models.CharField(max_length=64, verbose_name='Free text line 2', blank=True)),
                ('name_per_invoice', models.CharField(help_text="If your legal name is different to the name on your badge, fill this in, and we'll put it on your invoice. Otherwise, leave it blank.", max_length=64, verbose_name='Your legal name (for invoicing purposes)', blank=True)),
                ('of_legal_age', models.BooleanField(default=False, verbose_name='18+?')),
                ('dietary_requirements', models.CharField(max_length=256, blank=True)),
                ('accessibility_requirements', models.CharField(max_length=256, blank=True)),
                ('gender', models.CharField(max_length=64, blank=True)),
                ('profile', models.OneToOneField(to='registrasion.Attendee')),
            ],
        ),
        migrations.RemoveField(
            model_name='badge',
            name='profile',
        ),
        migrations.RemoveField(
            model_name='profile',
            name='user',
        ),
        migrations.DeleteModel(
            name='Badge',
        ),
        migrations.DeleteModel(
            name='Profile',
        ),
    ]
