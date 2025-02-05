#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Claudio Luck, Flavia Bastos, Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import json
import logging
import re
from decimal import Decimal

import dateutil.parser
from celery.exceptions import MaxRetriesExceededError
from django.conf import settings
from django.db import transaction
from django.db.models import Max, Min, Q
from django.db.models.functions import Length
from django.utils.timezone import now
from django.utils.translation import gettext_noop
from django_scopes import scope, scopes_disabled

from pretix.base.email import get_email_context
from pretix.base.i18n import language
from pretix.base.models import (
    Event, Invoice, Order, OrderPayment, OrderRefund, Organizer, Quota,
)
from pretix.base.payment import PaymentException
from pretix.base.services.locking import LockTimeoutException
from pretix.base.services.mail import SendMailException
from pretix.base.services.orders import change_payment_provider
from pretix.base.services.tasks import TransactionAwareTask
from pretix.celery_app import app

from .models import BankImportJob, BankTransaction

logger = logging.getLogger(__name__)


def notify_incomplete_payment(o: Order):
    with language(o.locale, o.event.settings.region):
        email_template = o.event.settings.mail_text_order_incomplete_payment
        email_context = get_email_context(event=o.event, order=o, pending_sum=o.pending_sum)
        email_subject = o.event.settings.mail_subject_order_incomplete_payment

        try:
            o.send_mail(
                email_subject, email_template, email_context,
                'pretix.event.order.email.expire_warning_sent'
            )
        except SendMailException:
            logger.exception('Reminder email could not be sent')


def cancel_old_payments(order):
    for p in order.payments.filter(
        state__in=(OrderPayment.PAYMENT_STATE_PENDING,
                   OrderPayment.PAYMENT_STATE_CREATED),
        provider='banktransfer',
    ):
        try:
            with transaction.atomic():
                p.payment_provider.cancel_payment(p)
                order.log_action('pretix.event.order.payment.canceled', {
                    'local_id': p.local_id,
                    'provider': p.provider,
                })
        except PaymentException as e:
            order.log_action(
                'pretix.event.order.payment.canceled.failed',
                {
                    'local_id': p.local_id,
                    'provider': p.provider,
                    'error': str(e)
                },
            )


def _find_order_for_code(base_qs, code):
    try_codes = [
        code,
        Order.normalize_code(code, is_fallback=True),
        code[:settings.ENTROPY['order_code']],
        Order.normalize_code(code[:settings.ENTROPY['order_code']], is_fallback=True)
    ]
    for c in try_codes:
        try:
            return base_qs.get(code=c)
        except Order.DoesNotExist:
            pass


def _find_order_for_invoice_id(base_qs, prefix, number):
    try:
        # Working with __iregex here is an experiment, if this turns out to be too slow in production
        # we might need to switch to a different approach.
        return base_qs.select_related('order').get(
            prefix__istartswith=prefix,  # redundant, but hopefully makes it a little faster
            full_invoice_no__iregex=prefix + r'[\- ]*0*' + number
        ).order
    except (Invoice.DoesNotExist, Invoice.MultipleObjectsReturned):
        pass


@transaction.atomic
def _handle_transaction(trans: BankTransaction, matches: tuple, event: Event = None, organizer: Organizer = None):
    orders = []
    if event:
        for slug, code in matches:
            order = _find_order_for_code(event.orders, code)
            if order:
                if order.code not in {o.code for o in orders}:
                    orders.append(order)
            else:
                order = _find_order_for_invoice_id(Invoice.objects.filter(event=event), slug, code)
                if order and order.code not in {o.code for o in orders}:
                    orders.append(order)
    else:
        qs = Order.objects.filter(event__organizer=organizer)
        for slug, code in matches:
            order = _find_order_for_code(qs.filter(event__slug__iexact=slug), code)
            if order:
                if order.code not in {o.code for o in orders}:
                    orders.append(order)
            else:
                order = _find_order_for_invoice_id(Invoice.objects.filter(event__organizer=organizer), slug, code)
                if order and order.code not in {o.code for o in orders}:
                    orders.append(order)

    if not orders:
        # No match
        trans.state = BankTransaction.STATE_NOMATCH
        trans.save()
        return
    else:
        trans.order = orders[0]

    if len(orders) > 1:
        # Multi-match! Can we split this automatically?
        order_pending_sum = sum(o.pending_sum for o in orders)
        if order_pending_sum != trans.amount:
            # we can't :( this needs to be dealt with by a human
            trans.state = BankTransaction.STATE_NOMATCH
            trans.message = gettext_noop('Automatic split to multiple orders not possible.')
            trans.save()
            return

        # we can!
        splits = [(o, o.pending_sum) for o in orders]
    else:
        splits = [(orders[0], trans.amount)]

    for o in orders:
        if o.status == Order.STATUS_PAID and o.pending_sum <= Decimal('0.00'):
            trans.state = BankTransaction.STATE_DUPLICATE
            trans.save()
            return
        elif o.status == Order.STATUS_CANCELED:
            trans.state = BankTransaction.STATE_ERROR
            trans.message = gettext_noop('The order has already been canceled.')
            trans.save()
            return

        if trans.currency is not None and trans.currency != o.event.currency:
            trans.state = BankTransaction.STATE_ERROR
            trans.message = gettext_noop('Currencies do not match.')
            trans.save()
            return

    trans.state = BankTransaction.STATE_VALID
    for order, amount in splits:
        info_data = {
            'reference': trans.reference,
            'date': trans.date_parsed.isoformat() if trans.date_parsed else trans.date,
            'payer': trans.payer,
            'iban': trans.iban,
            'bic': trans.bic,
            'full_amount': str(trans.amount),
            'trans_id': trans.pk
        }
        if amount < Decimal("0.00"):
            pending_refund = order.refunds.filter(
                amount=-amount,
                provider__in=('manual', 'banktransfer'),
                state__in=(OrderRefund.REFUND_STATE_CREATED, OrderRefund.REFUND_STATE_TRANSIT),
            ).first()
            existing_payment = order.payments.filter(
                provider='banktransfer',
                state__in=(OrderPayment.PAYMENT_STATE_CONFIRMED,),
            ).first()
            if pending_refund:
                pending_refund.provider = "banktransfer"
                pending_refund.info_data = {
                    **pending_refund.info_data,
                    **info_data,
                }
                pending_refund.done()
            elif existing_payment:
                existing_payment.create_external_refund(
                    amount=-amount,
                    info=json.dumps(info_data)
                )
            else:
                r = order.refunds.create(
                    state=OrderRefund.REFUND_STATE_EXTERNAL,
                    source=OrderRefund.REFUND_SOURCE_EXTERNAL,
                    amount=-amount,
                    order=order,
                    execution_date=now(),
                    provider='banktransfer',
                    info=json.dumps(info_data)
                )
                order.log_action('pretix.event.order.refund.created.externally', {
                    'local_id': r.local_id,
                    'provider': r.provider,
                })
            continue

        try:
            p, created = order.payments.get_or_create(
                amount=amount,
                provider='banktransfer',
                state__in=(OrderPayment.PAYMENT_STATE_CREATED, OrderPayment.PAYMENT_STATE_PENDING),
                defaults={
                    'state': OrderPayment.PAYMENT_STATE_CREATED,
                }
            )
        except OrderPayment.MultipleObjectsReturned:
            created = False
            p = order.payments.filter(
                amount=amount,
                provider='banktransfer',
                state__in=(OrderPayment.PAYMENT_STATE_CREATED, OrderPayment.PAYMENT_STATE_PENDING),
            ).last()

        p.info_data = {
            **p.info_data,
            **info_data,
        }

        if created:
            # We're perform a payment method switching on-demand here
            old_fee, new_fee, fee, p = change_payment_provider(order, p.payment_provider, p.amount,
                                                               new_payment=p, create_log=False)  # noqa
            if fee:
                p.fee = fee
                p.save(update_fields=['fee'])

        try:
            p.confirm()
        except Quota.QuotaExceededException:
            # payment confirmed but order status could not be set, no longer problem of this plugin
            cancel_old_payments(order)
        except SendMailException:
            # payment confirmed but order status could not be set, no longer problem of this plugin
            cancel_old_payments(order)
        else:
            cancel_old_payments(order)

            order.refresh_from_db()
            if order.pending_sum > Decimal('0.00') and order.status == Order.STATUS_PENDING:
                notify_incomplete_payment(order)

    trans.save()


def parse_date(date_str, region):
    try:
        return dateutil.parser.parse(
            date_str,
            dayfirst="." in date_str or region in ["GB"],
        ).date()
    except (ValueError, OverflowError):
        pass
    return None


def _get_unknown_transactions(job: BankImportJob, data: list, event: Event = None, organizer: Organizer = None):
    amount_pattern = re.compile("[^0-9.-]")
    known_checksums = set(t['checksum'] for t in BankTransaction.objects.filter(
        Q(event=event) if event else Q(organizer=organizer)
    ).values('checksum'))
    known_by_external_id = set((t['external_id'], t['date'], t['amount']) for t in BankTransaction.objects.filter(
        Q(event=event) if event else Q(organizer=organizer), external_id__isnull=False
    ).values('external_id', 'date', 'amount'))

    transactions = []
    for row in data:
        amount = row['amount']
        if not isinstance(amount, Decimal):
            if ',' in amount and '.' in amount:
                # Handle thousand-seperator , or .
                if amount.find(',') < amount.find('.'):
                    amount = amount.replace(',', '')
                else:
                    amount = amount.replace('.', '')
            amount = amount_pattern.sub("", amount.replace(',', '.'))
            try:
                amount = Decimal(amount)
            except:
                logger.exception('Could not parse amount of transaction: {}'.format(amount))
                amount = Decimal("0.00")

        trans = BankTransaction(event=event, organizer=organizer, import_job=job,
                                payer=row.get('payer', ''),
                                reference=row.get('reference', ''),
                                amount=amount,
                                date=row.get('date', ''),
                                iban=row.get('iban', ''),
                                bic=row.get('bic', ''),
                                external_id=row.get('external_id'),
                                currency=event.currency if event else job.currency)

        trans.date_parsed = parse_date(trans.date, event.settings.region or organizer.settings.region or None)

        trans.checksum = trans.calculate_checksum()
        if trans.checksum not in known_checksums and (not trans.external_id or (trans.external_id, trans.date, trans.amount) not in known_by_external_id):
            trans.state = BankTransaction.STATE_UNCHECKED
            trans.save()
            transactions.append(trans)

    return transactions


@app.task(base=TransactionAwareTask, bind=True, max_retries=5, default_retry_delay=1)
def process_banktransfers(self, job: int, data: list) -> None:
    with language("en"):  # We'll translate error messages at display time
        with scopes_disabled():
            job = BankImportJob.objects.get(pk=job)
        with scope(organizer=job.organizer or job.event.organizer):
            job.state = BankImportJob.STATE_RUNNING
            job.save()

            try:
                # Delete left-over transactions from a failed run before so they can reimported
                BankTransaction.objects.filter(state=BankTransaction.STATE_UNCHECKED, **job.owner_kwargs).delete()

                transactions = _get_unknown_transactions(job, data, **job.owner_kwargs)

                # Match order codes
                code_len_agg = Order.objects.filter(event__organizer=job.organizer).annotate(
                    clen=Length('code')
                ).aggregate(min=Min('clen'), max=Max('clen'))
                if job.event:
                    prefixes = {job.event.slug.upper()}
                else:
                    prefixes = {e.slug.upper() for e in job.organizer.events.all()}

                # Match invoice numbers
                inr_len_agg = Invoice.objects.filter(event__organizer=job.organizer).annotate(
                    clen=Length('invoice_no')
                ).aggregate(min=Min('clen'), max=Max('clen'))
                if job.event:
                    prefixes |= {p.rstrip(' -') for p in Invoice.objects.filter(event=job.event).distinct().values_list('prefix', flat=True)}
                else:
                    prefixes |= {p.rstrip(' -') for p in Invoice.objects.filter(event__organizer=job.organizer).distinct().values_list('prefix', flat=True)}

                pattern = re.compile(
                    "(%s)[ \\-_]*([A-Z0-9]{%s,%s})" % (
                        # We need to sort prefixes by length with long ones first. In case we have an event with slug
                        # "CONF" and one with slug "CONF2022", we want CONF2022 to match first, to avoid the parser
                        # thinking "2022" is already the order code.
                        "|".join(sorted([re.escape(p).replace("\\-", r"[\- ]*") for p in prefixes], key=lambda p: len(p), reverse=True)),
                        min(code_len_agg['min'] or 1, inr_len_agg['min'] or 1),
                        max(code_len_agg['max'] or 5, inr_len_agg['max'] or 5)
                    )
                )

                for trans in transactions:
                    # Whitespace in references is unreliable since linebreaks and spaces can occur almost anywhere, e.g.
                    # DEMOCON-123\n45 should be matched to DEMOCON-12345. However, sometimes whitespace is important,
                    # e.g. when there are two references. "DEMOCON-12345 DEMOCON-45678" would otherwise be parsed as
                    # "DEMOCON-12345DE" in some conditions. We'll naively take whatever has more matches.
                    matches_with_whitespace = pattern.findall(trans.reference.replace("\n", " ").upper())
                    matches_without_whitespace = pattern.findall(trans.reference.replace(" ", "").replace("\n", "").upper())

                    if len(matches_without_whitespace) > len(matches_with_whitespace):
                        matches = matches_without_whitespace
                    else:
                        matches = matches_with_whitespace

                    if matches:
                        if job.event:
                            _handle_transaction(trans, matches, event=job.event)
                        else:
                            _handle_transaction(trans, matches, organizer=job.organizer)
                    else:
                        trans.state = BankTransaction.STATE_NOMATCH
                        trans.save()
            except LockTimeoutException:
                try:
                    self.retry()
                except MaxRetriesExceededError:
                    logger.exception('Maximum number of retries exceeded for task.')
                    job.state = BankImportJob.STATE_ERROR
                    job.save()
            except Exception as e:
                job.state = BankImportJob.STATE_ERROR
                job.save()
                raise e
            else:
                job.state = BankImportJob.STATE_COMPLETED
                job.save()
