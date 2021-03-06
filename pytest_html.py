# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from base64 import b64encode
import cgi
import datetime
import os
import pkg_resources
import sys
import time

from py.xml import html, raw

# Python 2.X and 3.X compatibility
if sys.version_info[0] < 3:
    from codecs import open


def pytest_addoption(parser):
    group = parser.getgroup('terminal reporting')
    group.addoption('--html', action='store', dest='htmlpath',
                    metavar='path', default=None,
                    help='create html report file at given path.')


def pytest_configure(config):
    htmlpath = config.option.htmlpath
    # prevent opening htmlpath on slave nodes (xdist)
    if htmlpath and not hasattr(config, 'slaveinput'):
        config._html = HTMLReport(htmlpath)
        config.pluginmanager.register(config._html)


def pytest_unconfigure(config):
    html = getattr(config, '_html', None)
    if html:
        del config._html
        config.pluginmanager.unregister(html)


class HTMLReport(object):

    def __init__(self, logfile, environment=None):
        logfile = os.path.expanduser(os.path.expandvars(logfile))
        self.logfile = os.path.abspath(logfile)
        self.environment = environment or {}
        self.test_logs = []
        self.errors = self.failed = 0
        self.passed = self.skipped = 0
        self.xfailed = self.xpassed = 0

    def _appendrow(self, result, report):
        time = getattr(report, 'duration', 0.0)

        additional_html = []
        links_html = []

        if 'Passed' not in result:

            for extra in getattr(report, 'extra', []):
                href = None
                if type(extra) is Image:
                    href = '#'
                    image = 'data:image/png;base64,%s' % extra.content
                    additional_html.append(html.div(
                        html.a(html.img(src=image), href="#"),
                        class_='image'))
                elif type(extra) is HTML:
                    additional_html.append(extra.content)
                elif type(extra) is Text:
                    href = 'data:text/plain;charset=utf-8;base64,%s' % \
                        b64encode(extra.content)
                elif type(extra) is URL:
                    href = extra.content

                if href is not None:
                    links_html.append(html.a(
                        extra.name,
                        class_=extra.__class__.__name__.lower(),
                        href=href,
                        target='_blank'))
                    links_html.append(' ')

            if report.longrepr:
                log = html.div(class_='log')
                for line in str(report.longrepr).splitlines():
                    line = line.decode('utf-8')
                    separator = line.startswith('_ ' * 10)
                    if separator:
                        log.append(line[:80])
                    else:
                        exception = line.startswith("E   ")
                        if exception:
                            log.append(html.span(raw(cgi.escape(line)),
                                                 class_='error'))
                        else:
                            log.append(raw(cgi.escape(line)))
                    log.append(html.br())
                additional_html.append(log)

        self.test_logs.append(html.tr([
            html.td(result, class_='col-result'),
            html.td(report.nodeid, class_='col-name'),
            html.td('%.2f' % time, class_='col-duration'),
            html.td(links_html, class_='col-links'),
            html.td(additional_html, class_='extra')],
            class_=result.lower() + ' results-table-row'))

    def append_pass(self, report):
        self.passed += 1
        self._appendrow('Passed', report)

    def append_failure(self, report):
        if hasattr(report, "wasxfail"):
            self._appendrow('XPassed', report)
            self.xpassed += 1
        else:
            self._appendrow('Failed', report)
            self.failed += 1

    def append_error(self, report):
        self._appendrow('Error', report)
        self.errors += 1

    def append_skipped(self, report):
        if hasattr(report, "wasxfail"):
            self._appendrow('XFailed', report)
            self.xfailed += 1
        else:
            self._appendrow('Skipped', report)
            self.skipped += 1

    def pytest_runtest_logreport(self, report):
        if report.passed:
            if report.when == 'call':
                self.append_pass(report)
        elif report.failed:
            if report.when != "call":
                self.append_error(report)
            else:
                self.append_failure(report)
        elif report.skipped:
            self.append_skipped(report)

    def pytest_sessionstart(self, session):
        self.suite_start_time = time.time()

    def pytest_sessionfinish(self):
        if not os.path.exists(os.path.dirname(self.logfile)):
            os.makedirs(os.path.dirname(self.logfile))
        logfile = open(self.logfile, 'w', encoding='utf-8')
        suite_stop_time = time.time()
        suite_time_delta = suite_stop_time - self.suite_start_time
        numtests = self.passed + self.failed + self.xpassed + self.xfailed
        generated = datetime.datetime.now()

        head = html.head(
            html.meta(charset='utf-8'),
            html.title('Test Report'),
            html.style(raw(pkg_resources.resource_string(
                __name__, 'style.css'))))

        summary = [html.h2('Summary'), html.p(
            '%i tests ran in %.2f seconds.' % (numtests, suite_time_delta),
            html.br(),
            html.span('%i passed' % self.passed, class_='passed'), ', ',
            html.span('%i skipped' % self.skipped, class_='skipped'), ', ',
            html.span('%i failed' % self.failed, class_='failed'), ', ',
            html.span('%i errors' % self.errors, class_='error'), '.',
            html.br(),
            html.span('%i expected failures' % self.xfailed,
                      class_='skipped'), ', ',
            html.span('%i unexpected passes' % self.xpassed,
                      class_='failed'), '.')]

        results = [html.h2('Results'), html.table([html.thead(
            html.tr([
                html.th('Result', class_='sortable', col='result'),
                html.th('Test', class_='sortable', col='name'),
                html.th('Duration',
                        class_='sortable numeric',
                        col='duration'),
                html.th('Links')]), id='results-table-head'),
            html.tbody(*self.test_logs, id='results-table-body')],
            id='results-table')]

        body = html.body(
            html.script(raw(pkg_resources.resource_string(
                __name__, 'main.js'))),
            html.p('Report generated on %s at %s' % (
                generated.strftime('%d-%b-%Y'),
                generated.strftime('%H:%M:%S'))))

        if self.environment:
            body.append(html.h2('Environment'))
            body.append(html.table(
                [html.tr(html.td(k), html.td(v)) for k, v in sorted(
                    self.environment.items()) if v]),
                id='environment')

        body.extend(summary)
        body.extend(results)

        doc = html.html(head, body)

        logfile.write(u'<!DOCTYPE html>')
        logfile.write(doc.unicode(indent=2))
        logfile.close()

    def pytest_terminal_summary(self, terminalreporter):
        terminalreporter.write_sep('-', 'generated html file: %s' % (
            self.logfile))


class HTML(object):

    def __init__(self, content):
        self.content = content


class Image(object):

    def __init__(self, content, name='Image'):
        self.content = content
        self.name = name


class Text(object):

    def __init__(self, content, name='Text'):
        self.content = content
        self.name = name


class URL(object):

    def __init__(self, content, name='URL'):
        self.content = content
        self.name = name
