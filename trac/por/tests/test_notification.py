# -*- coding: utf-8 -*-

from trac.util.datefmt import utc
from trac.ticket.model import Ticket
from trac.ticket.notification import TicketNotifyEmail
from trac.test import EnvironmentStub, Mock, MockPerm
from trac.tests.notification import SMTPThreadedServer
from trac.tests.notification import parse_smtp_message
from trac.tests.notification import smtp_address

import os
import unittest

SMTP_TEST_PORT = 7000 + os.getpid() % 1000
MAXBODYWIDTH = 76



class NotificationTestCase(unittest.TestCase):
    """Notification test cases that send email over SMTP"""

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.env.config.set('project', 'name', 'TracTest')
        self.env.config.set('notification', 'smtp_enabled', 'true')
        self.env.config.set('notification', 'always_notify_owner', 'true')
        self.env.config.set('notification', 'always_notify_reporter', 'true')
        self.env.config.set('notification', 'smtp_always_cc',
                                                'frank.developer@example.org')
        # BBB: mark.customer@example.net chi è in always_cc viene notificato
        # sempre anche se non ha il permesso SENSITIVE_VIEW
        # è corretto?
        self.env.config.set('notification', 'use_public_cc', 'true')
        self.env.config.set('notification', 'smtp_port', str(SMTP_TEST_PORT))
        self.env.config.set('notification', 'smtp_server','localhost')
        self.req = Mock(href=self.env.href, abs_href=self.env.abs_href, tz=utc,
                        perm=MockPerm())
        self.smtpd = SMTPThreadedServer(SMTP_TEST_PORT)
        self.smtpd.start()

    def tearDown(self):
        """Signal the notification test suite that a test is over"""
        self.smtpd.cleanup()
        self.smtpd.stop()
        self.env.reset_db()

    def test_recipients(self):
        """To/Cc recipients"""
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.executemany("INSERT INTO permission VALUES (%s,%s)", [
                           ('frank.developer@example.org', 'SENSITIVE_VIEW'), 
                           ('joe.developer@example.org', 'SENSITIVE_VIEW'), 
                           ('jim.developer@example.org', 'SENSITIVE_VIEW'), 
                           ])
        ticket = Ticket(self.env)
        ticket['reporter'] = 'mary.customer@example.org'
        ticket['owner']    = 'joe.developer@example.org'
        ticket['cc']       = 'jim.developer@example.org, joe.customer@example.net, ' \
                             'jack.customer@example.net'
        ticket['summary'] = 'Foo'
        ticket['sensitive'] = '1'
        ticket.insert()
        tn = TicketNotifyEmail(self.env)
        tn.notify(ticket, newticket=True)
        recipients = self.smtpd.get_recipients()
        # checks there is no duplicate in the recipient list
        rcpts = []
        for r in recipients:
            self.failIf(r in rcpts)
            rcpts.append(r)
        # checks that all cc recipients have been notified
        cc_list = self.env.config.get('notification', 'smtp_always_cc')
        cc_list = "%s, %s" % (cc_list, ticket['cc'])
        for r in cc_list.replace(',', ' ').split():
            if 'customer' in r:
                self.failIf(r in recipients)
            else:
                self.failIf(r not in recipients)
        # checks that owner has not been notified
        self.failIf(smtp_address(ticket['owner']) not in recipients)
        # checks that reporter has not been notified (is a customer)
        self.failIf(smtp_address(ticket['reporter']) in recipients)
        

