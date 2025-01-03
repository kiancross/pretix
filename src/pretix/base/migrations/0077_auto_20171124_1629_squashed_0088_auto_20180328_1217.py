# Generated by Django 2.0.8 on 2018-09-11 14:50

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import F
from django.db.models.functions import Concat
from django.utils.crypto import get_random_string
from django.utils.translation import gettext as _

import pretix.base.models.auth
import pretix.base.validators
from pretix.base.i18n import language


def create_checkin_lists(apps, schema_editor):
    Event = apps.get_model('pretixbase', 'Event')
    Checkin = apps.get_model('pretixbase', 'Checkin')
    EventSettingsStore = apps.get_model('pretixbase', 'Event_SettingsStore')
    for e in Event.objects.all():
        locale = EventSettingsStore.objects.filter(object=e, key='locale').first()
        if locale:
            locale = locale.value
        else:
            locale = settings.LANGUAGE_CODE

        if e.has_subevents:
            for se in e.subevents.all():
                with language(locale):
                    cl = e.checkin_lists.create(name=se.name, subevent=se, all_products=True)
                Checkin.objects.filter(position__subevent=se, position__order__event=e).update(list=cl)
        else:
            with language(locale):
                cl = e.checkin_lists.create(name=_('Default list'), all_products=True)
            Checkin.objects.filter(position__order__event=e).update(list=cl)


def set_full_invoice_no(app, schema_editor):
    Invoice = app.get_model('pretixbase', 'Invoice')
    Invoice.objects.all().update(
        full_invoice_no=Concat(F('prefix'), F('invoice_no'))
    )


def set_position(apps, schema_editor):
    Question = apps.get_model('pretixbase', 'Question')
    for q in Question.objects.all():
        for i, option in enumerate(q.options.all()):
            option.position = i
            option.save()


def set_is_staff(apps, schema_editor):
    User = apps.get_model('pretixbase', 'User')
    User.objects.filter(is_superuser=True).update(is_staff=True)


def set_identifiers(apps, schema_editor):
    Question = apps.get_model('pretixbase', 'Question')
    QuestionOption = apps.get_model('pretixbase', 'QuestionOption')

    for q in Question.objects.select_related('event'):
        if not q.identifier:
            charset = list('ABCDEFGHJKLMNPQRSTUVWXYZ3789')
            while True:
                code = get_random_string(length=8, allowed_chars=charset)
                if not Question.objects.filter(event=q.event, identifier=code).exists():
                    q.identifier = code
                    q.save()
                    break

    for q in QuestionOption.objects.select_related('question', 'question__event'):
        if not q.identifier:
            charset = list('ABCDEFGHJKLMNPQRSTUVWXYZ3789')
            while True:
                code = get_random_string(length=8, allowed_chars=charset)
                if not QuestionOption.objects.filter(question__event=q.question.event, identifier=code).exists():
                    q.identifier = code
                    q.save()
                    break


class Migration(migrations.Migration):
    replaces = [('pretixbase', '0077_auto_20171124_1629'), ('pretixbase', '0078_auto_20171206_1603'),
                ('pretixbase', '0079_auto_20180115_0855'), ('pretixbase', '0080_question_ask_during_checkin'),
                ('pretixbase', '0081_auto_20180220_1031'), ('pretixbase', '0082_auto_20180222_0938'),
                ('pretixbase', '0083_auto_20180228_2102'), ('pretixbase', '0084_questionoption_position'),
                ('pretixbase', '0085_auto_20180312_1119'), ('pretixbase', '0086_auto_20180320_1219'),
                ('pretixbase', '0087_auto_20180317_1952'), ('pretixbase', '0088_auto_20180328_1217')]

    dependencies = [
        ('pretixbase', '0076_orderfee_squashed_0082_invoiceaddress_internal_reference'),
    ]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='slug',
            field=models.CharField(max_length=50, db_index=True, 
                help_text='Should be short, only contain lowercase letters, numbers, dots, and dashes, and must be '
                          'unique among your events. We recommend some kind of abbreviation or a date with less than '
                          '10 characters that can be easily remembered, but you can also choose to use a random '
                          'value. This will be used in URLs, order codes, invoice numbers, and bank transfer '
                          'references.',
                validators=[django.core.validators.RegexValidator(
                    message='The slug may only contain letters, numbers, dots and dashes.', regex='^[a-zA-Z0-9.-]+$'),
                    pretix.base.validators.EventSlugBanlistValidator()], verbose_name='Short form'),
        ),
        migrations.AlterField(
            model_name='eventmetaproperty',
            name='name',
            field=models.CharField(db_index=True,
                                   help_text='Can not contain spaces or special characters except underscores',
                                   max_length=50, validators=[django.core.validators.RegexValidator(
                    message='The property name may only contain letters, numbers and underscores.',
                    regex='^[a-zA-Z0-9_]+$')], verbose_name='Name'),
        ),
        migrations.AlterField(
            model_name='organizer',
            name='slug',
            field=models.CharField(max_length=50, db_index=True, 
                help_text='Should be short, only contain lowercase letters, numbers, dots, and dashes. Every slug can '
                          'only be used once. This is being used in URLs to refer to your organizer accounts and your'
                          ' events.',
                validators=[django.core.validators.RegexValidator(
                    message='The slug may only contain letters, numbers, dots and dashes.', regex='^[a-zA-Z0-9.-]+$'),
                    pretix.base.validators.OrganizerSlugBanlistValidator()], verbose_name='Short form'),
        ),
        migrations.CreateModel(
            name='CheckinList',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=190)),
                ('all_products',
                 models.BooleanField(default=True, verbose_name='All products (including newly created ones)')),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='checkin_lists',
                                            to='pretixbase.Event')),
                ('subevent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                               to='pretixbase.SubEvent', verbose_name='Date')),
                ('limit_products',
                 models.ManyToManyField(blank=True, to='pretixbase.Item', verbose_name='Limit to products')),
            ],
        ),
        migrations.AddField(
            model_name='checkin',
            name='list',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name='checkins', to='pretixbase.CheckinList'),
        ),
        migrations.RunPython(
            code=create_checkin_lists,
            reverse_code=django.db.migrations.operations.special.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='checkin',
            name='list',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='checkins',
                                    to='pretixbase.CheckinList'),
        ),
        migrations.CreateModel(
            name='NotificationSetting',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action_type', models.CharField(max_length=255)),
                ('method', models.CharField(choices=[('mail', 'Email')], max_length=255)),
                ('event', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                            to='pretixbase.Event')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('enabled', models.BooleanField(default=True)),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='notificationsetting',
            unique_together={('user', 'action_type', 'event', 'method')},
        ),
        migrations.AddField(
            model_name='logentry',
            name='visible',
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name='notificationsetting',
            name='event',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                    related_name='notification_settings', to='pretixbase.Event'),
        ),
        migrations.AlterField(
            model_name='notificationsetting',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notification_settings',
                                    to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='user',
            name='notifications_send',
            field=models.BooleanField(default=True, help_text='If turned off, you will not get any notifications.',
                                      verbose_name='Receive notifications according to my settings below'),
        ),
        migrations.AddField(
            model_name='user',
            name='notifications_token',
            field=models.CharField(default=pretix.base.models.auth.generate_notifications_token, max_length=255),
        ),
        migrations.AddField(
            model_name='invoice',
            name='full_invoice_no',
            field=models.CharField(db_index=True, default='', max_length=190),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='question',
            name='type',
            field=models.CharField(
                choices=[('N', 'Number'), ('S', 'Text (one line)'), ('T', 'Multiline text'), ('B', 'Yes/No'),
                         ('C', 'Choose one from a list'), ('M', 'Choose multiple from a list'), ('F', 'File upload'),
                         ('D', 'Date'), ('H', 'Time'), ('W', 'Date and time')], max_length=5,
                verbose_name='Question type'),
        ),
        migrations.RunPython(
            code=set_full_invoice_no,
            reverse_code=django.db.migrations.operations.special.RunPython.noop,
        ),
        migrations.AddField(
            model_name='question',
            name='ask_during_checkin',
            field=models.BooleanField(default=False,
                                      help_text='This will only work if you handle your check-in with pretixdroid 1.8 '
                                                'or '
                                                'newer or pretixdesk 0.2 or newer.',
                                      verbose_name='Ask during check-in instead of in the ticket buying process'),
        ),
        migrations.AddField(
            model_name='checkinlist',
            name='include_pending',
            field=models.BooleanField(default=False,
                                      help_text='With this option, people will be able to check in even if the order '
                                                'have '
                                                'not been paid. This only works with pretixdesk 0.3.0 or newer or '
                                                'pretixdroid 1.9 or newer.',
                                      verbose_name='Include pending orders'),
        ),
        migrations.AlterField(
            model_name='event',
            name='presale_end',
            field=models.DateTimeField(blank=True,
                                       help_text='Optional. No products will be sold after this date. If you do not '
                                                 'set '
                                                 'this value, the presale will end after the end date of your event.',
                                       null=True, verbose_name='End of presale'),
        ),
        migrations.AlterField(
            model_name='logentry',
            name='event',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    to='pretixbase.Event'),
        ),
        migrations.AlterField(
            model_name='subevent',
            name='presale_end',
            field=models.DateTimeField(blank=True,
                                       help_text='Optional. No products will be sold after this date. If you do not '
                                                 'set '
                                                 'this value, the presale will end after the end date of your event.',
                                       null=True, verbose_name='End of presale'),
        ),
        migrations.AlterField(
            model_name='user',
            name='require_2fa',
            field=models.BooleanField(default=False, verbose_name='Two-factor authentification is required to log in'),
        ),
        migrations.AddField(
            model_name='order',
            name='checkin_attention',
            field=models.BooleanField(default=False,
                                      help_text='If you set this, the check-in app will show a visible warning that '
                                                'tickets of this order require special attention. This will not show '
                                                'any '
                                                'details or custom message, so you need to brief your check-in staff '
                                                'how '
                                                'to handle these cases.',
                                      verbose_name='Requires special attention'),
        ),
        migrations.AddField(
            model_name='taxrule',
            name='custom_rules',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='orderfee',
            name='fee_type',
            field=models.CharField(
                choices=[('payment', 'Payment fee'), ('shipping', 'Shipping fee'), ('service', 'Service fee'),
                         ('other', 'Other fees')], max_length=100),
        ),
        migrations.AlterModelOptions(
            name='questionoption',
            options={'ordering': ('position', 'id'), 'verbose_name': 'Question option',
                     'verbose_name_plural': 'Question options'},
        ),
        migrations.AddField(
            model_name='questionoption',
            name='position',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='question',
            name='position',
            field=models.PositiveIntegerField(default=0, verbose_name='Position'),
        ),
        migrations.RunPython(
            code=set_position,
            reverse_code=django.db.migrations.operations.special.RunPython.noop,
        ),
        migrations.AddField(
            model_name='question',
            name='identifier',
            field=models.CharField(default='', max_length=190),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='questionoption',
            name='identifier',
            field=models.CharField(default='', max_length=190),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='user',
            name='locale',
            field=models.CharField(
                choices=[('en', 'English'), ('de', 'German'), ('de-informal', 'German (informal)'), ('nl', 'Dutch'),
                         ('da', 'Danish'), ('pt-br', 'Portuguese (Brazil)')], default='en', max_length=50,
                verbose_name='Language'),
        ),
        migrations.RunPython(
            code=set_identifiers,
            reverse_code=django.db.migrations.operations.special.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='cachedcombinedticket',
            name='file',
            field=models.FileField(blank=True, max_length=255, null=True,
                                   upload_to=pretix.base.models.orders.cachedcombinedticket_name),
        ),
        migrations.AlterField(
            model_name='cachedticket',
            name='file',
            field=models.FileField(blank=True, max_length=255, null=True,
                                   upload_to=pretix.base.models.orders.cachedticket_name),
        ),
        migrations.AlterField(
            model_name='invoice',
            name='file',
            field=models.FileField(blank=True, max_length=255, null=True,
                                   upload_to=pretix.base.models.invoices.invoice_filename),
        ),
        migrations.AlterField(
            model_name='question',
            name='identifier',
            field=models.CharField(
                help_text='You can enter any value here to make it easier to match the data with other sources. If '
                          'you do '
                          'not input one, we will generate one automatically.',
                max_length=190, verbose_name='Internal identifier'),
        ),
        migrations.AlterField(
            model_name='questionanswer',
            name='file',
            field=models.FileField(blank=True, max_length=255, null=True,
                                   upload_to=pretix.base.models.orders.answerfile_name),
        ),
        migrations.RunPython(
            code=set_is_staff,
            reverse_code=django.db.migrations.operations.special.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name='user',
            name='is_superuser',
        ),
        migrations.CreateModel(
            name='StaffSession',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_start', models.DateTimeField(auto_now_add=True)),
                ('date_end', models.DateTimeField(blank=True, null=True)),
                ('session_key', models.CharField(max_length=255)),
                ('comment', models.TextField()),
            ],
        ),
        migrations.CreateModel(
            name='StaffSessionAuditLog',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('datetime', models.DateTimeField(auto_now_add=True)),
                ('url', models.CharField(max_length=255)),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='logs',
                                              to='pretixbase.StaffSession')),
                ('impersonating', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                                    to=settings.AUTH_USER_MODEL)),
                ('method', models.CharField(default='GET', max_length=255)),
            ],
            options={
                'ordering': ('datetime',),
            },
        ),
        migrations.AddField(
            model_name='staffsession',
            name='user',
            field=models.ForeignKey(default=None, on_delete=django.db.models.deletion.CASCADE,
                                    to=settings.AUTH_USER_MODEL),
            preserve_default=False,
        ),
        migrations.AlterModelOptions(
            name='staffsession',
            options={'ordering': ('date_start',)},
        ),
        migrations.AlterField(
            model_name='item',
            name='picture',
            field=models.ImageField(blank=True, max_length=255, null=True,
                                    upload_to=pretix.base.models.items.itempicture_upload_to,
                                    verbose_name='Product picture'),
        ),
    ]
