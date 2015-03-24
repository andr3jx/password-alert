# Copyright 2014 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Frontend for receiving reports from the browser extension."""

__author__ = 'adhintz@google.com (Drew Hintz)'

from datetime import datetime
import logging
import urlparse

import auth
import config
import datastore
import password_change
import webapp2

from google.appengine.api import mail


EMAIL_ALERT_BODY = ('Display reports and set the alerting status for host: %s\n'
                    '%s\n\n'
                    'Display reports for user: %s\n'
                    '%s\n\n')

OTP_ALERT_SUBJECT = 'Password Catcher OTP alert: %s'
HOST_ALERT_SUBJECT = 'Password Catcher new host alert: %s'
# Subject prefix for alerts that look like a fake login page.
LOOKS_LIKE_GOOGLE = 'Looks like phishing! '

# The email for phishing alerts.
PHISHING_ALERT_SUBJECT = ('Password Catcher phishing page alert: %s')
PHISHING_ALERT_BODY = ('referer: %s\n\n'
                       'guessed user: %s\n\n'
                       'version: %s')


class Error(Exception):
  pass


class ReportPasswordHandler(webapp2.RequestHandler):
  """Saves reports from users to the datastore."""

  @auth.user_authorization_required
  def post(self):
    if 'X-Same-Domain' not in self.request.headers:
      logging.info('XSRF check failed.')
      return

    report = datastore.Report()
    report.url = self.request.get('url')[:datastore.MAX_STRING_LENGTH]
    split_url = urlparse.urlsplit(report.url)
    report.host = '%s://%s' % (split_url.scheme, split_url.netloc)
    report.referer = self.request.get('referer')[:datastore.MAX_STRING_LENGTH]
    report.email = self.request.get('email')
    host = datastore.Host.get_by_key_name(report.host)
    if not host or host.status == datastore.UNKNOWN:
      self.SendNewHostAlert(report)
    report.password_date = datetime.fromtimestamp(
        int(self.request.get('password_date')))  # password_date is in seconds
    if self.request.get('looksLikeGoogle'):
      report.looks_like_google = True
    if self.request.get('otp'):
      report.otp = True
      if not host or host.status == datastore.UNKNOWN:
        self.SendOtpAlert(report)
    report.put()
    password_change.ProcessReport(report, host)
    # returns 200 OK by default

  def _GetSearchUrl(self, host_or_email):
    return '%s/search/?search_query=%s' % (config.PASSWORDCATCHER_SERVER_URL,
                                           host_or_email)

  def SendNewHostAlert(self, report):
    """Email an alert about a new host."""
    if not config.PASSWORDCATCHER_ALERTS_EMAIL:
      return  # Email alerts not configured.
    message = mail.EmailMessage()
    message.sender = config.EMAIL_SENDER
    message.to = config.PASSWORDCATCHER_ALERTS_EMAIL
    message.subject = HOST_ALERT_SUBJECT % report.host
    message.body = EMAIL_ALERT_BODY % (
        report.host,
        self._GetSearchUrl(report.host),
        report.email,
        self._GetSearchUrl(report.email))
    message.send()

  def SendOtpAlert(self, report):
    """Email an OTP alert."""
    if not config.PASSWORDCATCHER_ALERTS_EMAIL:
      return  # Email alerts not configured.
    message = mail.EmailMessage()
    message.sender = config.EMAIL_SENDER
    message.to = config.PASSWORDCATCHER_ALERTS_EMAIL
    message.subject = OTP_ALERT_SUBJECT % report.host
    if report.looks_like_google:
      message.subject = LOOKS_LIKE_GOOGLE + message.subject
    message.body = EMAIL_ALERT_BODY % (
        report.host,
        self._GetSearchUrl(report.host),
        report.email,
        self._GetSearchUrl(report.email))
    message.send()


class ReportPageHandler(webapp2.RequestHandler):
  """Handles phishing page reports by emailing the alert email address."""

  def get(self):  # for debugging only
    self.post()

  @auth.user_authorization_required
  def post(self):
    if 'X-Same-Domain' not in self.request.headers:
      logging.info('XSRF check failed.')
      return

    logging.info('reportpage url: %s', self.request.get('url'))
    logging.info('reportpage referer: %s', self.request.get('referer'))
    if not config.PASSWORDCATCHER_ALERTS_EMAIL:
      return  # Email alerts not configured.
    message = mail.EmailMessage()
    message.sender = config.EMAIL_SENDER
    message.to = config.PASSWORDCATCHER_ALERTS_EMAIL
    message.subject = PHISHING_ALERT_SUBJECT % self.request.get('url')
    message.body = (PHISHING_ALERT_BODY
                    % (self.request.get('referer'),
                       self.request.get('username'),
                       self.request.get('version')))
    message.send()

application = webapp2.WSGIApplication([
    ('/report/password/', ReportPasswordHandler),
    ('/report/page/', ReportPageHandler)
])