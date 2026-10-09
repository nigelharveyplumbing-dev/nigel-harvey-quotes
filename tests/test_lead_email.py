"""Lead delivery failures, audit persistence, safe logs and authenticated retry."""

import base64
from email import message_from_string
import smtplib
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from local_browser_server import disposable_app


class LeadEmailTests(unittest.TestCase):
    def setUp(self):
        self.context = disposable_app('test-owner', 'test-secret',
                                      public_base_url='https://example.test')
        self.module, _ = self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)
        self.client = TestClient(self.module.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.headers = {'Authorization': 'Basic ' + base64.b64encode(
            b'test-owner:test-secret').decode()}
        self.payload = {'name': 'Test customer', 'phone': '000000',
                        'description': 'Shower replacement', 'postcode': 'GU1',
                        'urgency': 'planned', 'preferred_contact': 'whatsapp'}

    def create(self):
        response = self.client.post('/api/leads', json=self.payload)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def configured(self):
        return patch.multiple(self.module, EMAIL_ENABLED=True,
                              EMAIL_USER='owner@example.test', EMAIL_PASS='secret-value')

    def test_disabled_email_is_recorded_without_losing_lead(self):
        lead = self.create()
        result = self.client.get('/api/lead-email-status', headers=self.headers).json()
        self.assertFalse(result['configured'])
        self.assertIn('EMAIL_PASS', result['missing_settings'])
        self.assertEqual(result['notifications'][str(lead['id'])]['error_code'], 'not_configured')
        self.assertEqual(self.module.get_lead_by_id(lead['id'])['description'], self.payload['description'])

    def test_retry_recovers_failure_and_accepted_alert_is_not_resent(self):
        lead = self.create()
        with self.configured(), patch.object(self.module.smtplib, 'SMTP_SSL') as smtp:
            smtp.return_value.__enter__.return_value.sendmail.return_value = {}
            path = f"/api/leads/{lead['id']}/retry-email"
            response = self.client.post(path, headers=self.headers)
            self.assertEqual(response.json()['status'], 'accepted')
            self.assertEqual(self.client.post(path, headers=self.headers).json()['status'], 'accepted')
            smtp.assert_called_once()
            self.assertEqual(smtp.call_args.kwargs['timeout'], 15)
            raw = smtp.return_value.__enter__.return_value.sendmail.call_args.args[2]
            msg = message_from_string(raw)
            plain = msg.get_payload()[0].get_payload(decode=True).decode()
            for text in ['GU1', 'planned', 'whatsapp', 'https://example.test/app', 'Shower replacement']:
                self.assertIn(text, plain)
        state = self.module.lead_email_store.notification_states()[str(lead['id'])]
        self.assertEqual(state['attempts'], 2)
        self.assertEqual(state['status'], 'accepted')

    def test_authentication_failure_logs_no_credentials_or_customer_data(self):
        with self.configured(), patch.object(self.module.smtplib, 'SMTP_SSL',
                side_effect=smtplib.SMTPAuthenticationError(535, b'secret-value customer@example.test')), \
                self.assertLogs('business.notifications', level='ERROR') as logs:
            lead = self.create()
        self.assertIn('authentication_failed', ' '.join(logs.output))
        self.assertNotIn('secret-value', ' '.join(logs.output))
        self.assertNotIn('Test customer', ' '.join(logs.output))
        self.assertNotIn('customer@example.test', ' '.join(logs.output))
        self.assertEqual(self.module.lead_email_store.notification_states()[str(lead['id'])]['status'], 'failed')

    def test_mail_timeout_and_recipient_refusal_are_failures(self):
        for exception in [TimeoutError('private detail'), smtplib.SMTPRecipientsRefused({'private': (550, 'no')})]:
            with self.subTest(exception=type(exception).__name__), self.configured(), \
                    patch.object(self.module.smtplib, 'SMTP_SSL', side_effect=exception):
                lead = self.create()
            self.assertEqual(self.module.lead_email_store.notification_states()[str(lead['id'])]['status'], 'failed')

    def test_in_progress_retry_does_not_start_another_send(self):
        lead = self.create()
        conn = self.module.get_db()
        conn.execute("UPDATE lead_email_notifications SET status='sending', updated_at=? WHERE lead_id=?",
                     (time.time(), lead['id']))
        conn.commit()
        conn.close()
        with self.configured(), patch.object(self.module.smtplib, 'SMTP_SSL') as smtp:
            result = self.client.post(f"/api/leads/{lead['id']}/retry-email", headers=self.headers)
        self.assertEqual(result.json()['status'], 'sending')
        smtp.assert_not_called()

    def test_private_status_and_retry_are_protected(self):
        lead = self.create()
        self.assertEqual(self.client.get('/api/lead-email-status').status_code, 401)
        self.assertEqual(self.client.post(f"/api/leads/{lead['id']}/retry-email").status_code, 401)
        self.assertEqual(self.client.post('/api/leads/-1/retry-email', headers=self.headers).status_code, 404)
        response = self.client.post(f"/api/leads/{lead['id']}/retry-email",
                                   headers={**self.headers, 'Origin': 'https://other.test'})
        self.assertEqual(response.status_code, 403)

    def test_tracking_error_does_not_turn_saved_lead_into_failed_submission(self):
        with patch.object(self.module.lead_email_store, 'deliver', side_effect=RuntimeError('private')):
            lead = self.create()
        self.assertIsNotNone(self.module.get_lead_by_id(lead['id']))

    def test_stale_send_is_retryable_and_audit_survives_reinitialization(self):
        lead = self.create()
        conn = self.module.get_db()
        conn.execute("UPDATE lead_email_notifications SET status='sending', updated_at=? WHERE lead_id=?",
                     (time.time() - 180, lead['id']))
        conn.commit()
        conn.close()
        self.module.init_db()
        self.assertEqual(self.module.lead_email_store.notification_states()[str(lead['id'])]['status'], 'pending')
        with self.configured(), patch.object(self.module.smtplib, 'SMTP_SSL') as smtp:
            smtp.return_value.__enter__.return_value.sendmail.return_value = {}
            self.assertEqual(self.client.post(f"/api/leads/{lead['id']}/retry-email",
                                            headers=self.headers).json()['status'], 'accepted')
        self.assertEqual(self.module.get_lead_by_id(lead['id'])['status'], 'new')

    def test_sendmail_refused_mapping_is_not_marked_accepted(self):
        with self.configured(), patch.object(self.module.smtplib, 'SMTP_SSL') as smtp:
            smtp.return_value.__enter__.return_value.sendmail.return_value = {
                'owner@example.test': (550, 'rejected')}
            lead = self.create()
        self.assertEqual(self.module.lead_email_store.notification_states()[str(lead['id'])]['error_code'],
                         'recipient_refused')
