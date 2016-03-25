# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('registrasion', '0002_auto_20160323_2029'),
    ]

    operations = [
        migrations.AddField(
            model_name='badge',
            name='name_per_invoice',
            field=models.CharField(help_text="If your legal name is different to the name on your badge, fill this in, and we'll put it on your invoice. Otherwise, leave it blank.", max_length=64, verbose_name='Your legal name (for invoicing purposes)', blank=True),
        ),
        migrations.AlterField(
            model_name='badge',
            name='name',
            field=models.CharField(help_text="Your name, as you'd like it to appear on your badge. ", max_length=64, verbose_name='Your name (for your conference nametag)'),
        ),
    ]
