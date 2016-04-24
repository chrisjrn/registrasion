# -*- coding: utf-8 -*-
# Generated by Django 1.9.2 on 2016-04-11 02:57
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    replaces = [('registrasion', '0019_manualcreditnoterefund'), ('registrasion', '0020_auto_20160411_0256')]

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('registrasion', '0018_creditnote_creditnoteapplication_creditnoterefund_squashed_0019_auto_20160410_0753'),
    ]

    operations = [
        migrations.CreateModel(
            name='ManualCreditNoteRefund',
            fields=[
                ('entered_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('creditnoterefund_ptr', models.OneToOneField(auto_created=True, default=0, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='registrasion.CreditNoteRefund')),
            ],
        ),
    ]