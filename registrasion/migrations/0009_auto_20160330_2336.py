# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import datetime


class Migration(migrations.Migration):

    dependencies = [
        ('registrasion', '0008_cart_released'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='category',
            options={'verbose_name_plural': 'categories'},
        ),
        migrations.AlterModelOptions(
            name='timeorstocklimitenablingcondition',
            options={'verbose_name': 'ceiling'},
        ),
        migrations.AlterField(
            model_name='category',
            name='limit_per_user',
            field=models.PositiveIntegerField(help_text='The total number of items from this category one attendee may purchase.', null=True, verbose_name='Limit per user', blank=True),
        ),
        migrations.AlterField(
            model_name='category',
            name='render_type',
            field=models.IntegerField(help_text='The registration form will render this category in this style.', verbose_name='Render type', choices=[(1, 'Radio button'), (2, 'Quantity boxes')]),
        ),
        migrations.AlterField(
            model_name='category',
            name='required',
            field=models.BooleanField(help_text='If enabled, a user must select an item from this category.'),
        ),
        migrations.AlterField(
            model_name='categoryenablingcondition',
            name='enabling_category',
            field=models.ForeignKey(help_text='If a product from this category is purchased, this condition is met.', to='registrasion.Category'),
        ),
        migrations.AlterField(
            model_name='discountbase',
            name='description',
            field=models.CharField(help_text='A description of this discount. This will be included on invoices where this discount is applied.', max_length=255, verbose_name='Description'),
        ),
        migrations.AlterField(
            model_name='enablingconditionbase',
            name='categories',
            field=models.ManyToManyField(help_text='Categories whose products are enabled if this condition is met.', to='registrasion.Category', blank=True),
        ),
        migrations.AlterField(
            model_name='enablingconditionbase',
            name='mandatory',
            field=models.BooleanField(default=False, help_text='If there is at least one mandatory condition defined on a product or category, all such conditions must be met. Otherwise, at least one non-mandatory condition must be met.'),
        ),
        migrations.AlterField(
            model_name='enablingconditionbase',
            name='products',
            field=models.ManyToManyField(help_text='Products that are enabled if this condition is met.', to='registrasion.Product', blank=True),
        ),
        migrations.AlterField(
            model_name='includedproductdiscount',
            name='enabling_products',
            field=models.ManyToManyField(help_text='If one of these products are purchased, the discounts below will be enabled.', to='registrasion.Product', verbose_name='Including product'),
        ),
        migrations.AlterField(
            model_name='product',
            name='description',
            field=models.CharField(max_length=255, null=True, verbose_name='Description', blank=True),
        ),
        migrations.AlterField(
            model_name='product',
            name='reservation_duration',
            field=models.DurationField(default=datetime.timedelta(0, 3600), help_text='The length of time this product will be reserved before it is released for someone else to purchase.', verbose_name='Reservation duration'),
        ),
        migrations.AlterField(
            model_name='productenablingcondition',
            name='enabling_products',
            field=models.ManyToManyField(help_text='If one of these products are purchased, this condition is met.', to='registrasion.Product'),
        ),
        migrations.AlterField(
            model_name='timeorstocklimitdiscount',
            name='end_time',
            field=models.DateTimeField(help_text='This discount will only be available before this time.', null=True, verbose_name='End time', blank=True),
        ),
        migrations.AlterField(
            model_name='timeorstocklimitdiscount',
            name='limit',
            field=models.PositiveIntegerField(help_text='This discount may only be applied this many times.', null=True, verbose_name='Limit', blank=True),
        ),
        migrations.AlterField(
            model_name='timeorstocklimitdiscount',
            name='start_time',
            field=models.DateTimeField(help_text='This discount will only be available after this time.', null=True, verbose_name='Start time', blank=True),
        ),
        migrations.AlterField(
            model_name='timeorstocklimitenablingcondition',
            name='end_time',
            field=models.DateTimeField(help_text='Products included in this condition will only be available before this time.', null=True),
        ),
        migrations.AlterField(
            model_name='timeorstocklimitenablingcondition',
            name='limit',
            field=models.PositiveIntegerField(help_text='The number of items under this grouping that can be purchased.', null=True),
        ),
        migrations.AlterField(
            model_name='timeorstocklimitenablingcondition',
            name='start_time',
            field=models.DateTimeField(help_text='Products included in this condition will only be available after this time.', null=True),
        ),
    ]
