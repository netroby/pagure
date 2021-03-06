# -*- coding: utf-8 -*-

"""
 (c) 2015-2017 - Copyright Red Hat Inc

 Authors:
   Pierre-Yves Chibon <pingou@pingoured.fr>

"""

__requires__ = ['SQLAlchemy >= 0.8']
import pkg_resources

from unittest.case import SkipTest
import json
import unittest
import shutil
import sys
import os
try:
    import pyclamd
except ImportError:
    pyclamd = None
import tempfile
import re
from datetime import datetime, timedelta

import pygit2
from mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(
    os.path.abspath(__file__)), '..'))

import pagure
import pagure.lib
import tests


class PagureFlaskIssuestests(tests.Modeltests):
    """ Tests for flask issues controller of pagure """

    def setUp(self):
        """ Set up the environnment, run before every tests. """
        super(PagureFlaskIssuestests, self).setUp()

        pagure.APP.config['TESTING'] = True
        pagure.SESSION = self.session
        pagure.ui.SESSION = self.session
        pagure.ui.app.SESSION = self.session
        pagure.ui.issues.SESSION = self.session
        pagure.ui.repo.SESSION = self.session
        pagure.ui.filters.SESSION = self.session


    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_new_issue(self, p_send_email, p_ugt):
        """ Test the new_issue endpoint. """
        p_send_email.return_value = True
        p_ugt.return_value = True

        # No Git repo
        output = self.app.get('/foo/new_issue')
        self.assertEqual(output.status_code, 404)

        user = tests.FakeUser()
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/foo/new_issue')
            self.assertEqual(output.status_code, 404)

            tests.create_projects(self.session)
            tests.create_projects_git(
                os.path.join(self.path, 'repos'), bare=True)

            output = self.app.get('/test/new_issue')
            self.assertEqual(output.status_code, 200)
            self.assertTrue(
                '<div class="card-header">\n        New issue'
                in output.data)

            csrf_token = self.get_csrf(output=output)

            data = {
            }

            # Insufficient input
            output = self.app.post('/test/new_issue', data=data)
            self.assertEqual(output.status_code, 200)
            self.assertTrue(
                '<div class="card-header">\n        New issue'
                in output.data)
            self.assertEqual(output.data.count(
                'This field is required.'), 2)

            data['title'] = 'Test issue'
            output = self.app.post('/test/new_issue', data=data)
            self.assertEqual(output.status_code, 200)
            self.assertTrue(
                '<div class="card-header">\n        New issue'
                in output.data)
            self.assertEqual(output.data.count(
                'This field is required.'), 1)

            data['issue_content'] = 'We really should improve on this issue'
            data['status'] = 'Open'
            output = self.app.post('/test/new_issue', data=data)
            self.assertEqual(output.status_code, 200)
            self.assertTrue(
                '<div class="card-header">\n        New issue'
                in output.data)
            self.assertEqual(output.data.count(
                '</button>\n                      This field is required.'),
                0)

            # Invalid user
            data['csrf_token'] = csrf_token
            output = self.app.post('/test/new_issue', data=data)
            self.assertEqual(output.status_code, 404)
            self.assertIn(
                '<p>No such user found in the database: username</p>',
                output.data)

        # User not logged in
        output = self.app.get('/test/new_issue')
        self.assertEqual(output.status_code, 302)

        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            output = self.app.post(
                '/test/new_issue', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)

        # Project w/o issue tracker
        repo = pagure.get_authorized_project(self.session, 'test')
        repo.settings = {'issue_tracker': False}
        self.session.add(repo)
        self.session.commit()

        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            output = self.app.post(
                '/test/new_issue', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 404)

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_new_issue_w_file(self, p_send_email, p_ugt):
        """ Test the new_issue endpoint with a file. """
        p_send_email.return_value = True
        p_ugt.return_value = True

        tests.create_projects(self.session)
        tests.create_projects_git(
            os.path.join(self.path, 'repos'), bare=True)
        tests.create_projects_git(
            os.path.join(self.path, 'tickets'), bare=True)

        user = tests.FakeUser()
        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test/new_issue')
            self.assertEqual(output.status_code, 200)
            self.assertTrue(
                '<div class="card-header">\n        New issue'
                in output.data)

            csrf_token = self.get_csrf()

            with open(os.path.join(tests.HERE, 'placebo.png'), 'r') as stream:
                data = {
                    'title': 'Test issue',
                    'issue_content': 'We really should improve on this issue\n'
                                     '<!!image>',
                    'status': 'Open',
                    'filestream': stream,
                    'enctype': 'multipart/form-data',
                    'csrf_token': csrf_token,
                }

                output = self.app.post(
                    '/test/new_issue', data=data, follow_redirects=True)

            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)
            # Check the image was uploaded
            self.assertIn(
                'href="/test/issue/raw/'
                '8a06845923010b27bfd8e7e75acff7badc40d1021b4'
                '994e01f5e11ca40bc3abe',
                output.data)

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_new_issue_w_file_no_issue_tracker(self, p_send_email, p_ugt):
        """ Test the new_issue endpoint with a file. """
        p_send_email.return_value = True
        p_ugt.return_value = True

        tests.create_projects(self.session)
        tests.create_projects_git(
            os.path.join(self.path, 'repos'), bare=True)
        tests.create_projects_git(
            os.path.join(self.path, 'tickets'), bare=True)

        # Project w/o issue tracker
        repo = pagure.get_authorized_project(self.session, 'test')
        repo.settings = {'issue_tracker': False}
        self.session.add(repo)
        self.session.commit()

        user = tests.FakeUser()
        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            with open(os.path.join(tests.HERE, 'placebo.png'), 'r') as stream:
                data = {
                    'title': 'Test issue',
                    'issue_content': 'We really should improve on this issue',
                    'status': 'Open',
                    'filestream': stream,
                    'enctype': 'multipart/form-data',
                    'csrf_token': self.get_csrf(),
                }

                output = self.app.post(
                    '/test/new_issue', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 404)

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_new_issue_w_file_namespace(self, p_send_email, p_ugt):
        """ Test the new_issue endpoint with a file. """
        p_send_email.return_value = True
        p_ugt.return_value = True

        tests.create_projects(self.session)
        tests.create_projects_git(
            os.path.join(self.path, 'repos'), bare=True)
        tests.create_projects_git(
            os.path.join(self.path, 'tickets'), bare=True)

        # Project with a namespace
        user = tests.FakeUser()
        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/somenamespace/test3/new_issue')
            self.assertEqual(output.status_code, 200)
            self.assertTrue(
                '<div class="card-header">\n        New issue'
                in output.data)

            csrf_token = self.get_csrf()

            with open(os.path.join(tests.HERE, 'placebo.png'), 'r') as stream:
                data = {
                    'title': 'Test issue3',
                    'issue_content': 'We really should improve on this issue\n'
                                     '<!!image>',
                    'status': 'Open',
                    'filestream': stream,
                    'enctype': 'multipart/form-data',
                    'csrf_token': csrf_token,
                }

                output = self.app.post(
                    '/somenamespace/test3/new_issue', data=data, follow_redirects=True)

            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue3 - test3 - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/somenamespace/test3/issue/1/edit" '
                'title="Edit this issue">',
                output.data)
            # Check the image was uploaded
            self.assertIn(
                'href="/somenamespace/test3/issue/raw/'
                '8a06845923010b27bfd8e7e75acff7badc40d1021b4'
                '994e01f5e11ca40bc3abe',
                output.data)

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_new_issue_w_files(self, p_send_email, p_ugt):
        """ Test the new_issue endpoint with two files. """
        p_send_email.return_value = True
        p_ugt.return_value = True

        tests.create_projects(self.session)
        tests.create_projects_git(
            os.path.join(self.path, 'repos'), bare=True)
        tests.create_projects_git(
            os.path.join(self.path, 'tickets'), bare=True)

        user = tests.FakeUser()
        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test/new_issue')
            self.assertEqual(output.status_code, 200)
            self.assertTrue(
                '<div class="card-header">\n        New issue'
                in output.data)

            csrf_token = self.get_csrf()

            with open(
                    os.path.join(tests.HERE, 'placebo.png'), 'r'
                    ) as stream:
                with open(
                        os.path.join(tests.HERE, 'pagure.png'), 'r'
                        ) as stream2:
                    data = {
                        'title': 'Test issue',
                        'issue_content': 'We really should improve on this issue\n'
                                         '<!!image>\n<!!image>',
                        'status': 'Open',
                        'filestream': [stream, stream2],
                        'enctype': 'multipart/form-data',
                        'csrf_token': csrf_token,
                    }

                    output = self.app.post(
                        '/test/new_issue', data=data, follow_redirects=True)

            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)
            # Check the image was uploaded
            self.assertIn(
                'href="/test/issue/raw/'
                '8a06845923010b27bfd8e7e75acff7badc40d1021b4'
                '994e01f5e11ca40bc3abe',
                output.data)
            self.assertIn(
                'href="/test/issue/raw/'
                '6498a2de405546200b6144da56fc25d0a3976ae688d'
                'bfccaca609c8b4480523e',
                output.data)

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_new_issue_w_files_namespace(self, p_send_email, p_ugt):
        """ Test the new_issue endpoint with two files. """
        p_send_email.return_value = True
        p_ugt.return_value = True

        tests.create_projects(self.session)
        tests.create_projects_git(
            os.path.join(self.path, 'repos'), bare=True)
        tests.create_projects_git(
            os.path.join(self.path, 'tickets'), bare=True)

        # Project with a namespace
        user = tests.FakeUser()
        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/somenamespace/test3/new_issue')
            self.assertEqual(output.status_code, 200)
            self.assertTrue(
                '<div class="card-header">\n        New issue'
                in output.data)

            csrf_token = self.get_csrf()

            with open(
                    os.path.join(tests.HERE, 'placebo.png'), 'r'
                    ) as stream:
                with open(
                        os.path.join(tests.HERE, 'pagure.png'), 'r'
                        ) as stream2:

                    data = {
                        'title': 'Test issue3',
                        'issue_content': 'We really should improve on this issue\n'
                                         '<!!image>\n<!!image>',
                        'status': 'Open',
                        'filestream': [stream, stream2],
                        'enctype': 'multipart/form-data',
                        'csrf_token': csrf_token,
                    }

                    output = self.app.post(
                        '/somenamespace/test3/new_issue',
                        data=data, follow_redirects=True)

            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue3 - test3 - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/somenamespace/test3/issue/1/edit" '
                'title="Edit this issue">',
                output.data)
            # Check the image was uploaded
            self.assertIn(
                'href="/somenamespace/test3/issue/raw/'
                '8a06845923010b27bfd8e7e75acff7badc40d1021b4'
                '994e01f5e11ca40bc3abe',
                output.data)
            self.assertIn(
                'href="/somenamespace/test3/issue/raw/'
                '6498a2de405546200b6144da56fc25d0a3976ae688d'
                'bfccaca609c8b4480523e',
                output.data)

    def test_new_issue_metadata_user(self):
        """ Test the new_issue endpoint when the user has access to the
        project. """

        tests.create_projects(self.session)
        tests.create_projects_git(
            os.path.join(self.path, 'repos'), bare=True)
        tests.create_projects_git(
            os.path.join(self.path, 'tickets'), bare=True)

        user = tests.FakeUser()
        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test/new_issue')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<div class="card-header">\n        New issue',
                output.data)
            self.assertIn(
                '<label for="tag"><strong>Tags</strong></label>',
                output.data)
            self.assertIn(
                '<label for="assignee"><strong>Assignee</strong></label>',
                output.data)

    def test_new_issue_metadata_not_user(self):
        """ Test the new_issue endpoint when the user does not have access
        to the project. """

        tests.create_projects(self.session)
        tests.create_projects_git(
            os.path.join(self.path, 'repos'), bare=True)
        tests.create_projects_git(
            os.path.join(self.path, 'tickets'), bare=True)

        user = tests.FakeUser()
        user.username = 'foo'
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test/new_issue')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<div class="card-header">\n        New issue',
                output.data)
            self.assertNotIn(
                '<label for="tag"><strong>Tags</strong></label>',
                output.data)
            self.assertNotIn(
                '<label for="assignee"><strong>Assignee</strong></label>',
                output.data)

    @patch('pagure.lib.git.update_git', MagicMock(return_value=True))
    @patch('pagure.lib.notify.send_email', MagicMock(return_value=True))
    def test_new_issue_with_metadata(self):
        """ Test the new_issue endpoint when the user has access to the
        project. """

        tests.create_projects(self.session)
        tests.create_projects_git(
            os.path.join(self.path, 'repos'), bare=True)
        tests.create_projects_git(
            os.path.join(self.path, 'tickets'), bare=True)

        # Set some milestone
        repo = pagure.get_authorized_project(self.session, 'test')
        repo.milestones = {'v1.0': '', 'v2.0': 'Tomorrow!'}
        self.session.add(repo)
        self.session.commit()

        user = tests.FakeUser()
        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test/new_issue')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<div class="card-header">\n        New issue',
                output.data)
            self.assertIn(
                '<label for="tag"><strong>Tags</strong></label>',
                output.data)
            self.assertIn(
                '<label for="assignee"><strong>Assignee</strong></label>',
                output.data)

            csrf_token = self.get_csrf(output=output)

            data = {
                    'title': 'Test issue3',
                    'issue_content': 'We really should improve on this issue\n',
                    'status': 'Open',
                    'assignee': 'foo',
                    'milestone': 'v2.0',
                    'tag': 'tag2',
                    'csrf_token': csrf_token,
                }

            output = self.app.post(
                '/test/new_issue', data=data, follow_redirects=True)

            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue3 - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" '
                'title="Edit this issue">',
                output.data)
            # Check the metadata
            self.assertIn(
                'title="comma separated list of tags"\n                '
                'value="tag2" />', output.data)
            self.assertIn(
                'placeholder="username"\n              value="foo" />',
                output.data)
            self.assertIn(
                '<div id="milestone_plain">\n              <span >v2.0</span>',
                output.data)

    @patch('pagure.lib.git.update_git', MagicMock(return_value=True))
    @patch('pagure.lib.notify.send_email', MagicMock(return_value=True))
    def test_new_issue_with_metadata_not_user(self):
        """ Test the new_issue endpoint when the user does not have access
        to the project but still tries to.
        """

        tests.create_projects(self.session)
        tests.create_projects_git(
            os.path.join(self.path, 'repos'), bare=True)
        tests.create_projects_git(
            os.path.join(self.path, 'tickets'), bare=True)

        # Set some milestone
        repo = pagure.get_authorized_project(self.session, 'test')
        repo.milestones = {'v1.0': '', 'v2.0': 'Tomorrow!'}
        self.session.add(repo)
        self.session.commit()

        user = tests.FakeUser()
        user.username = 'foo'
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test/new_issue')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<div class="card-header">\n        New issue',
                output.data)
            self.assertNotIn(
                '<label for="tag"><strong>Tags</strong></label>',
                output.data)
            self.assertNotIn(
                '<label for="assignee"><strong>Assignee</strong></label>',
                output.data)

            csrf_token = self.get_csrf(output=output)

            data = {
                    'title': 'Test issue3',
                    'issue_content': 'We really should improve on this issue\n',
                    'status': 'Open',
                    'assignee': 'foo',
                    'milestone': 'v2.0',
                    'tag': 'tag2',
                    'csrf_token': csrf_token,
                }

            output = self.app.post(
                '/test/new_issue', data=data, follow_redirects=True)

            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue3 - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" '
                'title="Edit this issue">',
                output.data)
            # Check the metadata
            self.assertNotIn(
                'title="comma separated list of tags"\n                '
                'value="tag2" />', output.data)
            self.assertNotIn(
                'placeholder="username"\n              value="foo" />',
                output.data)
            self.assertNotIn(
                '<div id="milestone_plain">\n              <span >v2.0</span>',
                output.data)

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_view_issues(self, p_send_email, p_ugt):
        """ Test the view_issues endpoint. """
        p_send_email.return_value = True
        p_ugt.return_value = True

        output = self.app.get('/foo/issues')
        self.assertEqual(output.status_code, 404)

        tests.create_projects(self.session)
        tests.create_projects_git(
            os.path.join(self.path, 'repos'), bare=True)

        output = self.app.get('/test/issues')
        self.assertEqual(output.status_code, 200)
        self.assertIn(
            'div class="projectinfo m-t-1 m-b-1">\ntest project #1        '
            '</div>', output.data)
        self.assertTrue(
            '<h2>\n      0 Open Issues' in output.data)

        repo = pagure.get_authorized_project(self.session, 'test')
        # Create some custom fields to play with
        msg = pagure.lib.set_custom_key_fields(
            session=self.session,
            project=repo,
            fields=['test1'],
            types=['text'],
            data=[None],
            notify=[None]
        )
        self.session.commit()
        self.assertEqual(msg, 'List of custom fields updated')

        cfield = pagure.lib.get_custom_key(
            session=self.session,
            project=repo,
            keyname='test1')

        # Create issues to play with
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue',
            content='We should work on this',
            user='pingou',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue')

        msg = pagure.lib.set_custom_key_value(
            session=self.session,
            issue=msg,
            key=cfield,
            value='firstissue')
        self.session.commit()
        self.assertEqual(msg, 'Custom field test1 adjusted to firstissue')

        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue with milestone',
            content='Testing search',
            user='pingou',
            milestone='1.1',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue with milestone')

        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test invalid issue',
            content='This really is not related',
            user='pingou',
            status='Closed',
            close_status='Invalid',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test invalid issue')

        msg = pagure.lib.set_custom_key_value(
            session=self.session,
            issue=msg,
            key=cfield,
            value='second issue')
        self.session.commit()
        self.assertEqual(msg, 'Custom field test1 adjusted to second issue')

        # Whole list
        output = self.app.get('/test/issues')
        self.assertEqual(output.status_code, 200)
        self.assertIn('<title>Issues - test - Pagure</title>', output.data)
        self.assertTrue(
            '<h2>\n      2 Open Issues' in output.data)
        self.assertIn(
            '<div class="addrem_bar issues_pbar m-b-1 " title="33% of '
            'closed issues of total 3 issues">', output.data)
        self.assertIn(
            '<span style="width: 67%" title="67% of open issues of total '
            '3 issues">', output.data)
        # Verify that the sorting links are correct and the arrow is pointing
        # down next to the Opened column
        th_elements = re.findall(r'<th (?:id|class)=".*?">(.*?)</th>',
                                 output.data, re.M | re.S)
        href = ('href="/test/issues?status=Open&amp;order_key=title&amp;'
                'order=desc"')
        self.assertIn(href, th_elements[0])
        href = ('/test/issues?status=Open&amp;order_key=date_created&amp;'
                'order=asc"')
        self.assertIn(href, th_elements[1])
        arrow = '<span class="oi" data-glyph="arrow-thick-bottom"></span>'
        self.assertIn(arrow, th_elements[1])
        href = ('href="/test/issues?status=Open&amp;order_key=last_updated&'
                'amp;order=desc"')
        self.assertIn(href, th_elements[2])
        href = ('href="/test/issues?status=Open&amp;order_key=priority&amp;'
                'order=desc"')
        self.assertIn(href, th_elements[3])
        href = ('href="/test/issues?status=Open&amp;order_key=user&amp;'
                'order=desc"')
        self.assertIn(href, th_elements[4])
        href = ('href="/test/issues?status=Open&amp;order_key=assignee&amp;'
                'order=desc"')
        self.assertIn(href, th_elements[5])

        # Status = closed (all but open)
        output = self.app.get('/test/issues?status=cloSED')
        self.assertEqual(output.status_code, 200)
        self.assertIn('<title>Issues - test - Pagure</title>', output.data)
        self.assertTrue(
            '<h2>\n      1 Closed Issues' in output.data)
        self.assertIn(
            '<div class="addrem_bar issues_pbar m-b-1 closed" '
            'title="67% of open issues of total 3 issues">', output.data)
        self.assertIn(
            '<span style="width: 33%" title="33% of closed issues '
            'of total 3 issues">', output.data)

        # Status = fixed
        output = self.app.get('/test/issues?status=fixed')
        self.assertEqual(output.status_code, 200)
        self.assertIn('<title>Issues - test - Pagure</title>', output.data)
        self.assertTrue(
            '<h2>\n      0 Closed Issues' in output.data)

        # Status = Invalid
        output = self.app.get('/test/issues?status=Invalid')
        self.assertEqual(output.status_code, 200)
        self.assertIn('<title>Issues - test - Pagure</title>', output.data)
        self.assertTrue(
            '<h2>\n      1 Closed Issues' in output.data)

        # All tickets
        output = self.app.get('/test/issues?status=all')
        self.assertEqual(output.status_code, 200)
        self.assertIn('<title>Issues - test - Pagure</title>', output.data)
        self.assertTrue(
            '<h2>\n      3 Issues' in output.data)

        # Unicode search pattern
        output = self.app.get(
            '/test/issues?status=all&search_pattern=گروه')
        self.assertEqual(output.status_code, 200)
        self.assertIn('<title>Issues - test - Pagure</title>', output.data)
        self.assertIn('0 Issues', output.data)

        # Custom key searching
        output = self.app.get(
            '/test/issues?status=all&search_pattern=test1:firstissue')
        self.assertEqual(output.status_code, 200)
        self.assertIn('<title>Issues - test - Pagure</title>', output.data)
        self.assertIn('1 Issues', output.data)

        # Custom key searching with space
        output = self.app.get(
            '/test/issues?status=all&search_pattern=test1:"second issue"')
        self.assertEqual(output.status_code, 200)
        self.assertIn('<title>Issues - test - Pagure</title>', output.data)
        self.assertIn('1 Issues', output.data)

        # All tickets - different pagination
        before = pagure.APP.config['ITEM_PER_PAGE']
        pagure.APP.config['ITEM_PER_PAGE'] = 1
        output = self.app.get('/test/issues?status=all')
        self.assertEqual(output.status_code, 200)
        self.assertIn('<title>Issues - test - Pagure</title>', output.data)
        self.assertIn('<h2>\n      1 Issues (of 3)', output.data)
        self.assertIn(
            '<li class="active">page 1 of 3</li>', output.data)

        # All tickets - filtered for 1 - checking the pagination
        output = self.app.get(
            '/test/issues?status=all&search_pattern=invalid')
        self.assertEqual(output.status_code, 200)
        self.assertIn('<title>Issues - test - Pagure</title>', output.data)
        self.assertIn('<h2>\n      1 Issues (of 1)', output.data)
        self.assertIn(
            '<li class="active">page 1 of 1</li>', output.data)
        pagure.APP.config['ITEM_PER_PAGE'] = before

        # Search for issues with no milestone MARK
        output = self.app.get(
            '/test/issues?milestone=none')
        self.assertEqual(output.status_code, 200)
        self.assertIn('<title>Issues - test - Pagure</title>', output.data)
        self.assertIn('1 Open Issues (of 1)', output.data)

        # Search for issues with no milestone and milestone 1.1
        output = self.app.get(
            '/test/issues?milestone=none&milestone=1.1')
        self.assertEqual(output.status_code, 200)
        self.assertIn('<title>Issues - test - Pagure</title>', output.data)
        self.assertIn('2 Open Issues (of 2)', output.data)

        # Add another issue to test sorting
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Big problem!',
            content='I need help ASAP',
            user='foo',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Big problem!')

        # Sort by last_updated
        output = self.app.get('/test/issues?order_key=last_updated')
        tr_elements = re.findall(r'<tr>(.*?)</tr>', output.data, re.M | re.S)
        self.assertEqual(output.status_code, 200)
        arrowed_th = ('Modified</a>\n            <span class="oi" data-glyph='
                      '"arrow-thick-bottom"></span>')
        # First table row is the header
        self.assertIn(arrowed_th, tr_elements[0])
        # Make sure that issue four is first since it was modified last
        self.assertIn('href="/test/issue/4"', tr_elements[1])
        # Make sure that issue two is second since it was modified second
        self.assertIn('href="/test/issue/2"', tr_elements[2])
        # Make sure that issue one is last since it was modified first
        self.assertIn('href="/test/issue/1"', tr_elements[3])

        # Modify the date of the first issue and try again
        issue_one = pagure.lib.search_issues(self.session, repo, 1)
        issue_one.last_updated = datetime.utcnow() + timedelta(seconds=2)
        self.session.add(issue_one)
        self.session.commit()
        output = self.app.get('/test/issues?order_key=last_updated')
        tr_elements = re.findall(r'<tr>(.*?)</tr>', output.data, re.M | re.S)
        self.assertEqual(output.status_code, 200)
        # Make sure that issue one is first since it was modified last
        self.assertIn('href="/test/issue/1"', tr_elements[1])
        # Make sure that issue four is second since it was modified before
        # last
        self.assertIn('href="/test/issue/4"', tr_elements[2])
        # Make sure that issue two is last since it was modified before issue
        # one and four
        self.assertIn('href="/test/issue/2"', tr_elements[3])
        # Now query so that the results are ascending
        output = self.app.get('/test/issues?order_key=last_updated&order=asc')
        tr_elements = re.findall(r'<tr>(.*?)</tr>', output.data, re.M | re.S)
        arrowed_th = ('Modified</a>\n            <span class="oi" data-glyph='
                      '"arrow-thick-top"></span>')
        # First table row is the header
        self.assertIn(arrowed_th, tr_elements[0])
        self.assertIn('href="/test/issue/2"', tr_elements[1])
        self.assertIn('href="/test/issue/4"', tr_elements[2])
        self.assertIn('href="/test/issue/1"', tr_elements[3])

        # Sort by title descending
        output = self.app.get('/test/issues?order_key=title')
        tr_elements = re.findall(r'<tr>(.*?)</tr>', output.data, re.M | re.S)
        self.assertEqual(output.status_code, 200)
        arrowed_th = ('Issue</a>\n            <span class="oi" data-glyph='
                      '"arrow-thick-bottom"></span>')
        # First table row is the header
        self.assertIn(arrowed_th, tr_elements[0])
        self.assertIn('href="/test/issue/2"', tr_elements[1])
        self.assertIn('href="/test/issue/1"', tr_elements[2])
        self.assertIn('href="/test/issue/4"', tr_elements[3])

        # Sort by title ascending
        output = self.app.get('/test/issues?order_key=title&order=asc')
        tr_elements = re.findall(r'<tr>(.*?)</tr>', output.data, re.M | re.S)
        self.assertEqual(output.status_code, 200)
        arrowed_th = ('Issue</a>\n            <span class="oi" data-glyph='
                      '"arrow-thick-top"></span>')
        # First table row is the header
        self.assertIn(arrowed_th, tr_elements[0])
        self.assertIn('href="/test/issue/4"', tr_elements[1])
        self.assertIn('href="/test/issue/1"', tr_elements[2])
        self.assertIn('href="/test/issue/2"', tr_elements[3])

        # Sort by user (reporter/author) descending
        output = self.app.get('/test/issues?order_key=user&order=desc')
        tr_elements = re.findall(r'<tr>(.*?)</tr>', output.data, re.M | re.S)
        self.assertEqual(output.status_code, 200)
        arrowed_th = ('Reporter</a>\n            <span class="oi" data-glyph='
                      '"arrow-thick-bottom"></span>')
        # First table row is the header
        self.assertIn(arrowed_th, tr_elements[0])
        # Check for the name after the avatar
        self.assertIn('>\n                    pingou', tr_elements[1])
        # We check that they are unassigned, otherwise our previous check is
        # not specific enough as it can catch an assignee of "pingou"
        self.assertIn('unassigned', tr_elements[1])
        self.assertIn('>\n                    pingou', tr_elements[2])
        self.assertIn('unassigned', tr_elements[2])
        self.assertIn('>\n                    foo', tr_elements[3])
        self.assertIn('unassigned', tr_elements[3])

        # Sort by user (reporter/author) ascending
        output = self.app.get('/test/issues?order_key=user&order=asc')
        tr_elements = re.findall(r'<tr>(.*?)</tr>', output.data, re.M | re.S)
        self.assertEqual(output.status_code, 200)
        arrowed_th = ('Reporter</a>\n            <span class="oi" data-glyph='
                      '"arrow-thick-top"></span>')
        # First table row is the header
        self.assertIn(arrowed_th, tr_elements[0])
        # Check for the name after the avatar
        self.assertIn('>\n                    foo', tr_elements[1])
        # We check that they are unassigned, otherwise our previous check is
        # not specific enough as it can catch an assignee of "foo"
        self.assertIn('unassigned', tr_elements[1])
        self.assertIn('>\n                    pingou', tr_elements[2])
        self.assertIn('unassigned', tr_elements[2])
        self.assertIn('>\n                    pingou', tr_elements[3])
        self.assertIn('unassigned', tr_elements[3])

        # Set some assignees
        issues = self.session.query(pagure.lib.model.Issue).filter_by(
            status='Open').order_by(pagure.lib.model.Issue.id).all()
        issues[0].assignee_id = 1
        issues[1].assignee_id = 2
        issues[2].assignee_id = 1
        self.session.commit()

        # Sort by assignee descending
        output = self.app.get('/test/issues?order_key=assignee&order=desc')
        tr_elements = re.findall(r'<tr>(.*?)</tr>', output.data, re.M | re.S)
        self.assertEqual(output.status_code, 200)
        arrowed_th = ('Assignee</a>\n            <span class="oi" data-glyph='
                      '"arrow-thick-bottom"></span>')
        # First table row is the header
        self.assertIn(arrowed_th, tr_elements[0])
        # This detects the assignee but keying on if a certain link is present
        one = ('<a href="/test/issues?status=Open&amp;assignee=pingou"\n'
               '                  title="Filter issues by assignee">')
        two = ('<a href="/test/issues?status=Open&amp;assignee=pingou"\n'
               '                  title="Filter issues by assignee">')
        three = ('<a href="/test/issues?status=Open&amp;assignee=foo"\n'
                 '                  title="Filter issues by assignee">')
        self.assertIn(one, tr_elements[1])
        self.assertIn(two, tr_elements[2])
        self.assertIn(three, tr_elements[3])

        # Sort by assignee ascending
        output = self.app.get('/test/issues?order_key=assignee&order=asc')
        tr_elements = re.findall(r'<tr>(.*?)</tr>', output.data, re.M | re.S)
        self.assertEqual(output.status_code, 200)
        arrowed_th = ('Assignee</a>\n            <span class="oi" data-glyph='
                      '"arrow-thick-top"></span>')
        # First table row is the header
        self.assertIn(arrowed_th, tr_elements[0])
        # This detects the assignee but keying on if a certain link is present
        one = ('<a href="/test/issues?status=Open&amp;assignee=foo"\n'
               '                  title="Filter issues by assignee">')
        two = ('<a href="/test/issues?status=Open&amp;assignee=pingou"\n'
               '                  title="Filter issues by assignee">')
        three = ('<a href="/test/issues?status=Open&amp;assignee=pingou"\n'
                 '                  title="Filter issues by assignee">')
        self.assertIn(one, tr_elements[1])
        self.assertIn(two, tr_elements[2])
        self.assertIn(three, tr_elements[3])

        # New issue button is shown
        user = tests.FakeUser()
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                'class="btn btn-success btn-sm">New Issue</a>',
                output.data)

        # Project w/o issue tracker
        repo = pagure.get_authorized_project(self.session, 'test')
        repo.settings = {'issue_tracker': False}
        self.session.add(repo)
        self.session.commit()

        output = self.app.get('/test/issues')
        self.assertEqual(output.status_code, 404)

        # New issue button is hidden
        user = tests.FakeUser()
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test')
            self.assertEqual(output.status_code, 200)
            self.assertNotIn(
                'class="btn btn-success btn-sm">New Issue</a>',
                output.data)

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_search_issues_unicode(self, p_send_email, p_ugt):
        """ Test the view_issues endpoint filtering for an unicode char. """
        p_send_email.return_value = True
        p_ugt.return_value = True

        tests.create_projects(self.session)
        tests.create_projects_git(
            os.path.join(self.path, 'repos'), bare=True)

        repo = pagure.get_authorized_project(self.session, 'test')

        # Create 2 issues to play with
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title=u'Test issue ☃',
            content=u'We should work on this ❤',
            user='pingou',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, u'Test issue ☃')

        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue with milestone',
            content='Testing search',
            user='pingou',
            milestone='1.1',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue with milestone')

        # Whole list
        output = self.app.get('/test/issues')
        self.assertEqual(output.status_code, 200)
        self.assertIn('<title>Issues - test - Pagure</title>', output.data)
        self.assertTrue(
            '<h2>\n      2 Open Issues' in output.data)

        # Unicode search pattern
        output = self.app.get(
            '/test/issues?status=all&search_pattern=☃')
        self.assertEqual(output.status_code, 200)
        self.assertIn('<title>Issues - test - Pagure</title>', output.data)
        self.assertIn('1 Issues', output.data)

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_view_issue(self, p_send_email, p_ugt):
        """ Test the view_issue endpoint. """
        p_send_email.return_value = True
        p_ugt.return_value = True

        output = self.app.get('/foo/issue/1')
        self.assertEqual(output.status_code, 404)

        tests.create_projects(self.session)
        tests.create_projects_git(
            os.path.join(self.path, 'repos'), bare=True)

        output = self.app.get('/test/issue/1')
        self.assertEqual(output.status_code, 404)

        # Create issues to play with
        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue',
            content='We should work on this',
            user='pingou',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue')

        output = self.app.get('/test/issue/1')
        self.assertEqual(output.status_code, 200)
        # Not authentified = No edit
        self.assertNotIn(
            '<a class="btn btn-primary btn-sm" href="/test/issue/1/edit" '
            'title="Edit this issue">',
            output.data)
        self.assertTrue(
            '<a href="/login/?next=http%3A%2F%2Flocalhost%2Ftest%2Fissue%2F1">'
            'Login</a>\n            to comment on this ticket.'
            in output.data)

        user = tests.FakeUser()
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test/issue/1')
            self.assertEqual(output.status_code, 200)
            # Not author nor admin = No edit
            self.assertNotIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)
            self.assertNotIn(
                '<button class="btn btn-danger btn-sm" type="submit"',
                output.data)
            self.assertNotIn('title="Delete this ticket">', output.data)
            self.assertFalse(
                '<a href="/login/">Login</a> to comment on this ticket.'
                in output.data)
            # Not author nor admin = No take
            self.assertNotIn('function take_issue(){', output.data)
            self.assertNotIn('function drop_issue(){', output.data)
            self.assertNotIn(
                '<button class="btn btn-sm pull-xs-right" id="take-btn"',
                output.data)

        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test/issue/1')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)
            self.assertIn(
                '<button class="btn btn-danger btn-sm" type="submit"',
                output.data)
            self.assertIn('title="Delete this ticket">', output.data)

            csrf_token = self.get_csrf(output=output)

        # Create private issue
        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue',
            content='We should work on this',
            user='pingou',
            ticketfolder=None,
            private=True,
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue')

        # Not logged in
        output = self.app.get('/test/issue/2')
        self.assertEqual(output.status_code, 404)

        # Wrong user
        user = tests.FakeUser()
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test/issue/2')
            self.assertEqual(output.status_code, 404)

        # reporter
        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test/issue/2')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #2: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<span class="oi red-icon" data-glyph="lock-locked" '
                'title="Private issue"></span>', output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/2/edit" title="Edit this issue">',
                output.data)

        # Project w/o issue tracker
        repo = pagure.get_authorized_project(self.session, 'test')
        repo.settings = {'issue_tracker': False}
        self.session.add(repo)
        self.session.commit()

        output = self.app.get('/test/issue/1')
        self.assertEqual(output.status_code, 404)

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_view_issue_user_ticket(self, p_send_email, p_ugt):
        """ Test the view_issue endpoint. """
        p_send_email.return_value = True
        p_ugt.return_value = True

        output = self.app.get('/foo/issue/1')
        self.assertEqual(output.status_code, 404)

        tests.create_projects(self.session)
        tests.create_projects_git(
            os.path.join(self.path, 'repos'), bare=True)

        output = self.app.get('/test/issue/1')
        self.assertEqual(output.status_code, 404)

        # Create issues to play with
        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue',
            content='We should work on this',
            user='pingou',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue')

        output = self.app.get('/test/issue/1')
        self.assertEqual(output.status_code, 200)
        # Not authentified = No edit
        self.assertNotIn(
            '<a class="btn btn-primary btn-sm" href="/test/issue/1/edit" '
            'title="Edit this issue">',
            output.data)
        self.assertTrue(
            '<a href="/login/?next=http%3A%2F%2Flocalhost%2Ftest%2Fissue%2F1">'
            'Login</a>\n            to comment on this ticket.'
            in output.data)

        # Create issues to play with
        repo = pagure.get_authorized_project(self.session, 'test')

        # Add user 'foo' with ticket access on repo
        msg = pagure.lib.add_user_to_project(
            self.session,
            repo,
            new_user='foo',
            user='pingou',
            access='ticket',
        )
        self.assertEqual(msg, 'User added')
        self.session.commit()

        user = tests.FakeUser(username='foo')
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test/issue/1')
            self.assertEqual(output.status_code, 200)
            # Not author nor admin = No edit
            self.assertNotIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)
            self.assertNotIn(
                '<button class="btn btn-danger btn-sm" type="submit"',
                output.data)
            self.assertNotIn('title="Delete this ticket">', output.data)
            self.assertFalse(
                '<a href="/login/">Login</a> to comment on this ticket.'
                in output.data)
            # user has ticket = take ok
            self.assertIn('function take_issue(){', output.data)
            self.assertIn('function drop_issue(){', output.data)
            self.assertIn(
                '<button class="btn btn-sm pull-xs-right" id="take-btn"',
                output.data)

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_view_issue_custom_field_user_ticket(self, p_send_email, p_ugt):
        """ Test the view_issue endpoint. """
        p_send_email.return_value = True
        p_ugt.return_value = True

        output = self.app.get('/foo/issue/1')
        self.assertEqual(output.status_code, 404)

        tests.create_projects(self.session)
        tests.create_projects_git(
            os.path.join(self.path, 'repos'), bare=True)

        output = self.app.get('/test/issue/1')
        self.assertEqual(output.status_code, 404)

        # Create issues to play with
        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue',
            content='We should work on this',
            user='pingou',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue')

        # Add user 'foo' with ticket access on repo
        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.add_user_to_project(
            self.session,
            repo,
            new_user='foo',
            user='pingou',
            access='ticket',
        )
        self.assertEqual(msg, 'User added')
        self.session.commit()

        # Set some custom fields
        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.set_custom_key_fields(
            self.session,
            repo,
            ['bugzilla', 'upstream', 'reviewstatus'],
            ['link', 'boolean', 'list'],
            ['unused data for non-list type', '', 'ack, nack ,  needs review'],
            [None, None, None])
        self.session.commit()
        self.assertEqual(msg, 'List of custom fields updated')

        # User with no rights
        user = tests.FakeUser()
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test/issue/1')
            self.assertEqual(output.status_code, 200)
            self.assertNotIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)
            self.assertNotIn(
                '<button class="btn btn-danger btn-sm" type="submit"',
                output.data)
            self.assertNotIn('title="Delete this ticket">', output.data)
            # user no ACLs = no take action/button
            self.assertNotIn('function take_issue(){',output.data)
            self.assertNotIn('function drop_issue(){',output.data)
            self.assertNotIn(
                '<button class="btn btn-sm pull-xs-right" id="take-btn"',
                output.data)

            # user no ACLs = no metadata form
            self.assertNotIn(
                '<input                  class="form-control" '
                'name="bugzilla" id="bugzilla"/>',output.data)
            self.assertNotIn(
                '<select class="form-control" name="reviewstatus" '
                'id="reviewstatus>',output.data)
            self.assertNotIn(
                '<input type="checkbox"                   '
                'class="form-control" name="upstream" id="upstream"/>',
                output.data)

        user = tests.FakeUser(username='foo')
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test/issue/1')
            self.assertEqual(output.status_code, 200)
            self.assertNotIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)
            self.assertNotIn(
                '<button class="btn btn-danger btn-sm" type="submit"',
                output.data)
            self.assertNotIn('title="Delete this ticket">', output.data)
            self.assertFalse(
                '<a href="/login/">Login</a> to comment on this ticket.'
                in output.data)
            # user has ticket = take ok
            self.assertIn('function take_issue(){',output.data)
            self.assertIn('function drop_issue(){',output.data)
            self.assertIn(
                '<button class="btn btn-sm pull-xs-right" id="take-btn"',
                output.data)

            # user has ticket == Sees the metadata
            self.assertIn(
                '<input                  class="form-control" '
                'name="bugzilla" id="bugzilla"/>',output.data)
            self.assertIn(
                '<select class="form-control"\n'
                '                    name="reviewstatus"\n'
                '                    id="reviewstatus">\n',
                output.data)
            self.assertIn(
                '<input type="checkbox"                   '
                'class="form-control" name="upstream" id="upstream"/>',
                output.data)

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_view_issue_non_ascii_milestone(self, p_send_email, p_ugt):
        """ Test the view_issue endpoint with non-ascii milestone. """
        p_send_email.return_value = True
        p_ugt.return_value = True

        output = self.app.get('/foo/issue/1')
        self.assertEqual(output.status_code, 404)

        tests.create_projects(self.session)
        tests.create_projects_git(
            os.path.join(self.path, 'repos'), bare=True)

        output = self.app.get('/test/issue/1')
        self.assertEqual(output.status_code, 404)

        # Create issues to play with
        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue',
            content='We should work on this',
            user='pingou',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue')

        # Add a non-ascii milestone to the issue but project has no milestone
        issue = pagure.lib.search_issues(self.session, repo, issueid=1)
        message = pagure.lib.edit_issue(
            self.session,
            issue=issue,
            milestone=b'käpy'.decode('utf-8'),
            private=False,
            user='pingou',
            ticketfolder=None
        )
        self.assertEqual(
            message,
            [
                u'Issue set to the milestone: k\xe4py'
            ]
        )
        self.session.commit()

        output = self.app.get('/test/issue/1')
        self.assertEqual(output.status_code, 200)
        self.assertIn(
            '<title>Issue #1: Test issue - test - Pagure</title>',
            output.data)
        self.assertNotIn(b'käpy'.decode('utf-8'), output.data)

        # Add a non-ascii milestone to the project
        repo = pagure.get_authorized_project(self.session, 'test')
        repo.milestones = {b'käpy'.decode('utf-8'): None}
        self.session.add(repo)
        self.session.commit()

        # View the issue
        output = self.app.get('/test/issue/1')
        self.assertEqual(output.status_code, 200)
        self.assertIn(
            '<title>Issue #1: Test issue - test - Pagure</title>',
            output.data)
        self.assertIn(b'käpy'.decode('utf-8'), output.data.decode('utf-8'))

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_view_issue_list_no_data(self, p_send_email, p_ugt):
        """ Test the view_issue endpoint when the issue has a custom field
        of type list with no data attached. """
        p_send_email.return_value = True
        p_ugt.return_value = True

        tests.create_projects(self.session)
        tests.create_projects_git(
            os.path.join(self.path, 'repos'), bare=True)

        repo = pagure.get_authorized_project(self.session, 'test')

        # Add custom fields to the project
        msg = pagure.lib.set_custom_key_fields(
            session=self.session,
            project=repo,
            fields=['test1'],
            types=['list'],
            data=[None],
            notify=[None]
        )
        self.session.commit()
        self.assertEqual(msg, 'List of custom fields updated')

        # Create issues to play with
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue',
            content='We should work on this',
            user='pingou',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue')

        # Assign a value to the custom key on that ticket
        cfield = pagure.lib.get_custom_key(
            session=self.session,
            project=repo,
            keyname='test1')
        msg = pagure.lib.set_custom_key_value(
            session=self.session,
            issue=msg,
            key=cfield,
            value='item')
        self.session.commit()
        self.assertEqual(msg, 'Custom field test1 adjusted to item')

        user = tests.FakeUser()
        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test/issue/1')
            self.assertEqual(output.status_code, 200)

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_update_issue(self, p_send_email, p_ugt):
        """ Test the update_issue endpoint. """
        p_send_email.return_value = True
        p_ugt.return_value = True

        # No Git repo
        output = self.app.get('/foo/issue/1/update')
        self.assertEqual(output.status_code, 404)

        tests.create_projects(self.session)
        tests.create_projects_git(
            os.path.join(self.path, 'repos'), bare=True)

        output = self.app.get('/test/issue/1/update')
        self.assertEqual(output.status_code, 302)

        # Create issues to play with
        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue',
            content='We should work on this',
            user='pingou',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue')

        user = tests.FakeUser()
        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test/issue/1')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)
            self.assertEqual(output.data.count('title="PY C (pingou)"'), 1)

            csrf_token = self.get_csrf(output=output)

            data = {
                'status': 'Closed',
                'close_status': 'fixed'
            }

            # Invalid repo
            output = self.app.post('/bar/issue/1/update', data=data)
            self.assertEqual(output.status_code, 404)

            # Non-existing issue
            output = self.app.post('/test/issue/100/update', data=data)
            self.assertEqual(output.status_code, 404)

            output = self.app.post(
                '/test/issue/1/update', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)
            self.assertFalse(
                '<option selected value="Fixed">Fixed</option>'
                in output.data)

            # Right status, wrong csrf
            data['close_status'] = 'Fixed'
            output = self.app.post(
                '/test/issue/1/update', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)
            self.assertFalse(
                '<option selected value="Fixed">Fixed</option>'
                in output.data)

            # working status update
            data['csrf_token'] = csrf_token
            output = self.app.post(
                '/test/issue/1/update', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)
            self.assertIn(
                '</button>\n                      '
                'Issue close_status updated to: Fixed\n',
                output.data)
            self.assertIn(
                '</button>\n                      '
                'Issue status updated to: Closed (was: Open)\n',
                output.data)
            self.assertTrue(
                '<option selected value="Fixed">Fixed</option>'
                in output.data)
            # FIXME: There is likely something going wrong in the html
            # below
            self.assertIn(
                '<small><p><strong>Metadata Update from '\
'<a href="https://pagure.org/user/pingou"> </a>'\
'''<a href="https://pagure.org/user/pingou"> @pingou</a></strong>:<br>
- Issue close_status updated to: Fixed<br>
- Issue status updated to: Closed (was: Open)</p></small>''',
                output.data)

            # Add new comment
            data = {
                'csrf_token': csrf_token,
                'status': 'Closed',
                'close_status': 'Fixed',
                'comment': 'Woohoo a second comment!',
            }
            output = self.app.post(
                '/test/issue/1/update', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)
            self.assertIn(
                '</button>\n                      Comment added',
                output.data)
            self.assertNotIn(
                '</button>\n                      No changes to edit',
                output.data)
            self.assertTrue(
                '<p>Woohoo a second comment!</p>' in output.data)
            self.assertEqual(output.data.count('comment_body">'), 2)
            self.assertTrue(
                '<option selected value="Fixed">Fixed</option>'
                in output.data)
            # 2: one for the original comment, one for the new comment
            self.assertEqual(output.data.count('title="PY C (pingou)"'), 2)

            # Add new tag
            data = {
                'csrf_token': csrf_token,
                'status': 'Closed',
                'close_status': 'Fixed',
                'tag': 'tag2',
            }
            output = self.app.post(
                '/test/issue/1/update', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)
            self.assertTrue(
                '<p>Woohoo a second comment!</p>' in output.data)
            self.assertEqual(output.data.count('comment_body">'), 2)
            self.assertTrue(
                '<option selected value="Fixed">Fixed</option>'
                in output.data)

            # Assign issue to an non-existent user
            data = {
                'csrf_token': csrf_token,
                'status': 'Closed',
                'close_status': 'Fixed',
                'assignee': 'ralph',
            }
            output = self.app.post(
                '/test/issue/1/update', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)
            self.assertIn(
                '</button>\n                      No user &#34;ralph&#34; found',
                output.data)
            self.assertTrue(
                '<p>Woohoo a second comment!</p>' in output.data)
            self.assertEqual(output.data.count('comment_body">'), 2)
            self.assertTrue(
                '<option selected value="Fixed">Fixed</option>'
                in output.data)

            # Assign issue properly
            data = {
                'csrf_token': csrf_token,
                'status': 'Closed',
                'close_status': 'Fixed',
                'assignee': 'pingou',
            }
            output = self.app.post(
                '/test/issue/1/update', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)
            self.assertIn(
                '</button>\n                      Issue assigned to pingou\n',
                output.data)
            self.assertTrue(
                '<a href="/test/issues?assignee=pingou" title="PY C (pingou)"' in output.data)
            self.assertTrue(
                '<p>Woohoo a second comment!</p>' in output.data)
            self.assertEqual(output.data.count('comment_body">'), 2)
            self.assertTrue(
                '<option selected value="Fixed">Fixed</option>'
                in output.data)

        # Create another issue with a dependency
        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue',
            content='We should work on this',
            user='pingou',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue')

        # Reset the status of the first issue
        parent_issue = pagure.lib.search_issues(
            self.session, repo, issueid=1)
        parent_issue.status = 'Open'
        self.session.add(parent_issue)
        # Add the dependency relationship
        self.session.add(parent_issue)
        issue = pagure.lib.search_issues(self.session, repo, issueid=2)
        issue.parents.append(parent_issue)
        self.session.add(issue)
        self.session.commit()

        with tests.user_set(pagure.APP, user):

            data['csrf_token'] = csrf_token
            output = self.app.post(
                '/test/issue/2/update', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #2: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/2/edit" title="Edit this issue">',
                output.data)
            self.assertIn(
                '</button>\n                      You cannot close a ticket '
                'that has ticket depending that are still open.',
                output.data)
            self.assertTrue(
                '<option selected value="Open">Open</option>'
                in output.data)

        # Create private issue
        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue',
            content='We should work on this',
            user='pingou',
            ticketfolder=None,
            private=True,
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue')

        # Wrong user
        user = tests.FakeUser()
        with tests.user_set(pagure.APP, user):
            output = self.app.post(
                '/test/issue/3/update', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 403)

        # Project w/o issue tracker
        repo = pagure.get_authorized_project(self.session, 'test')
        repo.settings = {'issue_tracker': False}
        self.session.add(repo)
        self.session.commit()

        with tests.user_set(pagure.APP, user):
            # Repo not set-up for issue tracker
            output = self.app.post('/test/issue/1/update', data=data)
            self.assertEqual(output.status_code, 404)

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_update_issue_drop_comment(self, p_send_email, p_ugt):
        """ Test droping comment via the update_issue endpoint. """
        p_send_email.return_value = True
        p_ugt.return_value = True

        tests.create_projects(self.session)
        tests.create_projects_git(
            os.path.join(self.path, 'repos'), bare=True)

        # Create issues to play with
        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue',
            content='We should work on this',
            user='pingou',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue')

        user = tests.FakeUser()
        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test/issue/1')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)

            csrf_token = self.get_csrf(output=output)

            # Add new comment
            data = {
                'csrf_token': csrf_token,
                'comment': 'Woohoo a second comment!',
            }
            output = self.app.post(
                '/test/issue/1/update', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)
            self.assertIn(
                '</button>\n                      Comment added',
                output.data)
            self.assertTrue(
                '<p>Woohoo a second comment!</p>' in output.data)
            self.assertEqual(output.data.count('comment_body">'), 2)

        repo = pagure.get_authorized_project(self.session, 'test')
        issue = pagure.lib.search_issues(self.session, repo, issueid=1)
        self.assertEqual(len(issue.comments), 1)

        data = {
            'csrf_token': csrf_token,
            'drop_comment': 1,
        }

        user = tests.FakeUser()
        with tests.user_set(pagure.APP, user):
            # Wrong issue id
            output = self.app.post(
                '/test/issue/3/update', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 404)

            # Wrong user
            output = self.app.post(
                '/test/issue/1/update', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 403)

        user = tests.FakeUser()
        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            # Drop the new comment
            output = self.app.post(
                '/test/issue/1/update', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)
            self.assertIn(
                '</button>\n                      Comment removed',
                output.data)

            # Drop non-existant comment
            output = self.app.post(
                '/test/issue/1/update', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 404)

        repo = pagure.get_authorized_project(self.session, 'test')
        issue = pagure.lib.search_issues(self.session, repo, issueid=1)
        self.assertEqual(len(issue.comments), 0)

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_update_issue_depend(self, p_send_email, p_ugt):
        """ Test adding dependency via the update_issue endpoint. """
        p_send_email.return_value = True
        p_ugt.return_value = True

        tests.create_projects(self.session)
        tests.create_projects_git(
            os.path.join(self.path, 'repos'), bare=True)

        # Create issues to play with
        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue',
            content='We should work on this',
            user='pingou',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue')

        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue #2',
            content='We should work on this again',
            user='foo',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue #2')

        user = tests.FakeUser()
        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test/issue/1')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)

            csrf_token = self.get_csrf(output=output)

            # Add a dependent ticket
            data = {
                'csrf_token': csrf_token,
                'depending': '2',
            }
            output = self.app.post(
                '/test/issue/1/update', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)

            # Add an invalid dependent ticket
            data = {
                'csrf_token': csrf_token,
                'depending': '2,abc',
            }
            output = self.app.post(
                '/test/issue/1/update', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)
            self.assertNotIn(
                '</button>\n                      '
                'Successfully edited issue #1',
                output.data)

        repo = pagure.get_authorized_project(self.session, 'test')
        issue = pagure.lib.search_issues(self.session, repo, issueid=1)
        self.assertEqual(issue.depending_text, [2])
        self.assertEqual(issue.blocking_text, [])

        # Check the icons showing if the issues are blocking/blocked
        output = self.app.get('/test/issues/')
        self.assertEqual(
            output.data.count(
                '<span class="oi" data-glyph="lock-unlocked" title="Issue '
                'blocking one or more issue(s)"></span>'),
            1)
        self.assertEqual(
            output.data.count(
                '<span class="oi" data-glyph="ban" title="Issue blocked '
                'by one or more issue(s)"></span>'),
            1)

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_update_issue_block(self, p_send_email, p_ugt):
        """ Test adding blocked issue via the update_issue endpoint. """
        p_send_email.return_value = True
        p_ugt.return_value = True

        tests.create_projects(self.session)
        tests.create_projects_git(
            os.path.join(self.path, 'repos'), bare=True)

        # Create issues to play with
        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue',
            content='We should work on this',
            user='pingou',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue')

        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue #2',
            content='We should work on this again',
            user='foo',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue #2')

        # User is not an admin of the project
        user = tests.FakeUser(username='foo')
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test/issue/1')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)

            csrf_token = self.get_csrf(output=output)

            # Add a dependent ticket
            data = {
                'csrf_token': csrf_token,
                'blocking': '2',
            }
            output = self.app.post(
                '/test/issue/1/update', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)

            repo = pagure.get_authorized_project(self.session, 'test')
            issue = pagure.lib.search_issues(self.session, repo, issueid=1)
            self.assertEqual(issue.depending_text, [])
            self.assertEqual(issue.blocking_text, [])

        user = tests.FakeUser()
        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test/issue/1')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)

            csrf_token = self.get_csrf(output=output)

            # Add a dependent ticket
            data = {
                'csrf_token': csrf_token,
                'blocking': '2',
            }
            output = self.app.post(
                '/test/issue/1/update', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)

            # Add an invalid dependent ticket
            data = {
                'csrf_token': csrf_token,
                'blocking': '2,abc',
            }
            output = self.app.post(
                '/test/issue/1/update', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)
            self.assertNotIn(
                '</button>\n                      '
                'Successfully edited issue #1',
                output.data)

        repo = pagure.get_authorized_project(self.session, 'test')
        issue = pagure.lib.search_issues(self.session, repo, issueid=1)
        self.assertEqual(issue.depending_text, [])
        self.assertEqual(issue.blocking_text, [2])

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_upload_issue(self, p_send_email, p_ugt):
        """ Test the upload_issue endpoint. """
        p_send_email.return_value = True
        p_ugt.return_value = True

        tests.create_projects(self.session)
        tests.create_projects_git(
            os.path.join(self.path, 'repos'), bare=True)
        tests.create_projects_git(
            os.path.join(self.path, 'tickets'), bare=True)

        # Create issues to play with
        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue',
            content='We should work on this',
            user='pingou',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue')

        user = tests.FakeUser()
        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test/issue/1')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)

            csrf_token = self.get_csrf(output=output)

            output = self.app.post('/foo/issue/1/upload')
            self.assertEqual(output.status_code, 404)

            output = self.app.post('/test/issue/100/upload')
            self.assertEqual(output.status_code, 404)

            # Invalid upload
            data = {
                'enctype': 'multipart/form-data',
            }
            output = self.app.post(
                '/test/issue/1/upload', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            json_data = json.loads(output.data)
            exp = {'output': 'notok'}
            self.assertDictEqual(json_data, exp)

            # Attach a file to a ticket
            with open(os.path.join(tests.HERE, 'placebo.png'), 'rb') as stream:
                data = {
                    'csrf_token': csrf_token,
                    'filestream': stream,
                    'enctype': 'multipart/form-data',
                }
                output = self.app.post(
                    '/test/issue/1/upload', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            json_data = json.loads(output.data)

            folder = os.path.dirname(
                os.path.abspath(__file__))[1:].replace('/', '_')
            exp = {
                'filelocations': [
                    '/test/issue/raw/files/8a06845923010b27bfd8'
                    'e7e75acff7badc40d1021b4994e01f5e11ca40bc3a'
                    'be-%s_placebo.png' % folder
                ],
                'filenames': ['%s_placebo.png' % folder],
                'output': 'ok'
            }
            self.assertDictEqual(json_data, exp)

        # Project w/o issue tracker
        repo = pagure.get_authorized_project(self.session, 'test')
        repo.settings = {'issue_tracker': False}
        self.session.add(repo)
        self.session.commit()

        with tests.user_set(pagure.APP, user):
            output = self.app.post('/test/issue/1/upload')
            self.assertEqual(output.status_code, 404)

    @patch.dict('pagure.APP.config', {'PR_ONLY': True})
    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_upload_issue_virus(self, p_send_email, p_ugt):
        """ Test the upload_issue endpoint. """
        if not pyclamd:
            raise SkipTest()
        p_send_email.return_value = True
        p_ugt.return_value = True

        tests.create_projects(self.session)
        tests.create_projects_git(
            os.path.join(self.path, 'repos'), bare=True)
        tests.create_projects_git(
            os.path.join(self.path, 'tickets'), bare=True)

        # Create issues to play with
        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue',
            content='We should work on this',
            user='pingou',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue')

        user = tests.FakeUser()
        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            csrf_token = self.get_csrf()

            # TODO: Figure a way to enable this test on jenkins
            # Try to attach a virus
            if not os.environ.get('BUILD_ID'):
                with tempfile.NamedTemporaryFile() as eicarfile:
                    eicarfile.write(pyclamd.ClamdUnixSocket().EICAR())
                    eicarfile.flush()
                    with open(eicarfile.name, 'rb') as stream:
                        data = {
                            'csrf_token': csrf_token,
                            'filestream': stream,
                            'enctype': 'multipart/form-data',
                        }
                        output = self.app.post(
                            '/test/issue/1/upload', data=data, follow_redirects=True)
                    self.assertEqual(output.status_code, 200)
                    json_data = json.loads(output.data)
                    exp = {
                        'output': 'notok',
                    }
                    self.assertDictEqual(json_data, exp)

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_upload_issue_two_files(self, p_send_email, p_ugt):
        """ Test the upload_issue endpoint with two files. """
        p_send_email.return_value = True
        p_ugt.return_value = True

        tests.create_projects(self.session)
        tests.create_projects_git(
            os.path.join(self.path, 'repos'), bare=True)
        tests.create_projects_git(
            os.path.join(self.path, 'tickets'), bare=True)

        # Create issues to play with
        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue',
            content='We should work on this',
            user='pingou',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue')

        user = tests.FakeUser()
        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            csrf_token = self.get_csrf()

            # Attach two files to a ticket
            with open(os.path.join(tests.HERE, 'placebo.png'), 'rb') as stream:
                with open(os.path.join(tests.HERE, 'placebo.png'), 'rb') as stream2:
                    data = {
                        'csrf_token': csrf_token,
                        'filestream': [stream, stream2],
                        'enctype': 'multipart/form-data',
                    }
                    output = self.app.post(
                        '/test/issue/1/upload', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            json_data = json.loads(output.data)

            folder = os.path.dirname(
                os.path.abspath(__file__))[1:].replace('/', '_')
            exp = {
                'output': 'ok',
                'filelocations': [
                    '/test/issue/raw/files/8a06845923010b27bfd8'
                    'e7e75acff7badc40d1021b4994e01f5e11ca40bc3a'
                    'be-%s_placebo.png' % folder,
                    '/test/issue/raw/files/8a06845923010b27bfd8'
                    'e7e75acff7badc40d1021b4994e01f5e11ca40bc3a'
                    'be-%s_placebo.png' % folder,
                ],
                'filenames': [
                    '%s_placebo.png' % folder,
                    '%s_placebo.png' % folder
                ],
            }
            self.assertDictEqual(json_data, exp)

    def test_view_issue_raw_file_empty(self):
        """ Test the view_issue_raw_file endpoint. """
        # Create the project and git repos
        tests.create_projects(self.session)
        tests.create_projects_git(
            os.path.join(self.path, 'tickets'), bare=True)

        # Create issues to play with
        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue',
            content='We should work on this',
            user='pingou',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue')

        url = '/issue/raw/8a06845923010b27bfd8'\
            'e7e75acff7badc40d1021b4994e01f5e11ca40bc3a'\
            'be-home_pierrey_repos_gitrepo_pagure_tests'\
            '_placebo.png'

        output = self.app.get('/foo' + url)
        self.assertEqual(output.status_code, 404)

        output = self.app.get('/test' + url)
        self.assertEqual(output.status_code, 404)

        # Project w/o issue tracker
        repo = pagure.get_authorized_project(self.session, 'test')
        repo.settings = {'issue_tracker': False}
        self.session.add(repo)
        self.session.commit()

        output = self.app.get('/test' + url)
        self.assertEqual(output.status_code, 404)

    def test_view_issue_raw_file(self):
        """ Test the view_issue_raw_file endpoint. """
        # Create the issue and upload to it
        self.test_upload_issue()

        # Project w/ issue tracker
        repo = pagure.get_authorized_project(self.session, 'test')
        repo.settings = {'issue_tracker': True}
        self.session.add(repo)
        self.session.commit()

        url = '/issue/raw/8a06845923010b27bfd8'\
            'e7e75acff7badc40d1021b4994e01f5e11ca40bc3a'\
            'be-%s_placebo.png' % os.path.dirname(
                os.path.abspath(__file__))[1:].replace('/', '_')

        output = self.app.get('/foo' + url)
        self.assertEqual(output.status_code, 404)

        output = self.app.get('/test/issue/raw/test.png')
        self.assertEqual(output.status_code, 404)

        # Access file by name
        output = self.app.get('/test' + url)
        self.assertEqual(output.status_code, 200)

        # Project w/o issue tracker
        repo = pagure.get_authorized_project(self.session, 'test')
        repo.settings = {'issue_tracker': False}
        self.session.add(repo)
        self.session.commit()

        output = self.app.get('/test' + url)
        self.assertEqual(output.status_code, 404)

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_edit_issue(self, p_send_email, p_ugt):
        """ Test the edit_issue endpoint. """
        p_send_email.return_value = True
        p_ugt.return_value = True

        # No Git repo
        output = self.app.get('/foo/issue/1/edit')
        self.assertEqual(output.status_code, 404)

        user = tests.FakeUser()
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/foo/issue/1/edit')
            self.assertEqual(output.status_code, 404)

            tests.create_projects(self.session)
            tests.create_projects_git(
                os.path.join(self.path, 'repos'), bare=True)

            output = self.app.get('/test/issue/1/edit')
            self.assertEqual(output.status_code, 404)

        # User not logged in
        output = self.app.get('/foo/issue/1/edit')
        self.assertEqual(output.status_code, 404)

        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test/issue/1/edit')
            self.assertEqual(output.status_code, 404)

        # Create issues to play with
        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue',
            content='We should work on this',
            user='pingou',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue')

        user = tests.FakeUser()
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test/issue/1/edit')
            self.assertEqual(output.status_code, 403)

        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test/issue/1/edit')
            self.assertEqual(output.status_code, 200)
            self.assertTrue(
                '<div class="card-header">\n        Edit '
                'issue #1\n      </div>' in output.data)

            csrf_token = self.get_csrf(output=output)

            data = {
                'issue_content': 'We should work on this!'
            }

            output = self.app.post('/test/issue/1/edit', data=data)
            self.assertEqual(output.status_code, 200)
            self.assertTrue(
                '<div class="card-header">\n        Edit '
                'issue #1\n      </div>' in output.data)
            self.assertEqual(output.data.count(
                '<small>\n            This field is required.&nbsp;\n'
                '          </small>'), 1)
            self.assertEqual(output.data.count(
                '<small>\n            Not a valid choice&nbsp;'
                '\n          </small>'), 1)

            data['status'] = 'Open'
            data['title'] = 'Test issue #1'
            output = self.app.post('/test/issue/1/edit', data=data)
            self.assertEqual(output.status_code, 200)
            self.assertTrue(
                '<div class="card-header">\n        Edit '
                'issue #1\n      </div>' in output.data)
            self.assertEqual(output.data.count(
                '<small>\n            This field is required.&nbsp;\n'
                '          </small>'), 0)
            self.assertEqual(output.data.count(
                '<small>\n            Not a valid choice&nbsp;'
                '\n          </small>'), 0)

            data['csrf_token'] = csrf_token
            output = self.app.post(
                '/test/issue/1/edit', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<span class="issueid label label-default">#1</span>\n'
                '    <span id="issuetitle">Test issue #1</span>',
                output.data)
            self.assertEqual(output.data.count(
                '<option selected value="Open">Open</option>'), 1)
            self.assertEqual(output.data.count('comment_body">'), 1)
            self.assertEqual(output.data.count(
                '<p>We should work on this!</p>'), 1)

        # Project w/o issue tracker
        repo = pagure.get_authorized_project(self.session, 'test')
        repo.settings = {'issue_tracker': False}
        self.session.add(repo)
        self.session.commit()

        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            output = self.app.post('/test/issue/1/edit', data=data)
            self.assertEqual(output.status_code, 404)

    @patch('pagure.lib.git.update_git', MagicMock(return_value=True))
    @patch('pagure.lib.notify.send_email', MagicMock(return_value=True))
    def test_edit_issue_no_change(self):
        """ Test the edit_issue endpoint. """

        tests.create_projects(self.session)
        tests.create_projects_git(
            os.path.join(self.path, 'repos'), bare=True)

        # Create an issue to play with
        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue',
            content='We should work on this',
            user='pingou',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue')

        user = tests.FakeUser(username = 'pingou')
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test/issue/1/edit')
            self.assertEqual(output.status_code, 200)
            self.assertTrue(
                '<div class="card-header">\n        Edit '
                'issue #1\n      </div>' in output.data)

            csrf_token = self.get_csrf(output=output)

            # Change nothing in the issue
            data = {
                'issue_content': 'We should work on this',
                'status': 'Open',
                'title': 'Test issue',
                'csrf_token': csrf_token
            }

            output = self.app.post(
                '/test/issue/1/edit', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<span class="issueid label label-default">#1</span>\n'
                '    <span id="issuetitle">Test issue</span>',
                output.data)
            self.assertEqual(output.data.count(
                '<option selected value="Open">Open</option>'), 1)
            self.assertEqual(output.data.count('comment_body">'), 1)
            self.assertEqual(output.data.count(
                '<p>We should work on this</p>'), 1)

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_edit_tag(self, p_send_email, p_ugt):
        """ Test the edit_tag endpoint. """
        p_send_email.return_value = True
        p_ugt.return_value = True

        # No Git repo
        output = self.app.get('/foo/tag/foo/edit')
        self.assertEqual(output.status_code, 404)

        user = tests.FakeUser()
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/foo/tag/foo/edit')
            self.assertEqual(output.status_code, 404)

            tests.create_projects(self.session)
            tests.create_projects_git(os.path.join(self.path, 'repos'))

            output = self.app.get('/test/tag/foo/edit')
            self.assertEqual(output.status_code, 403)

        # User not logged in
        output = self.app.get('/test/tag/foo/edit')
        self.assertEqual(output.status_code, 302)

        # Create issues to play with
        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue',
            content='We should work on this',
            user='pingou',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue')

        # Add a tag to the issue
        issue = pagure.lib.search_issues(self.session, repo, issueid=1)
        msg = pagure.lib.add_tag_obj(
            session=self.session,
            obj=issue,
            tags='tag1',
            user='pingou',
            gitfolder=None)
        self.session.commit()
        self.assertEqual(msg, 'Issue tagged with: tag1')

        # Before edit, list tags
        tags = pagure.lib.get_tags_of_project(self.session, repo)
        self.assertEqual([tag.tag for tag in tags], ['tag1'])

        # Edit tag
        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            #Edit a tag that doesn't exit
            output = self.app.get('/test/tag/does_not_exist/edit')
            self.assertEqual(output.status_code, 404)

            output = self.app.get('/test/tag/tag1/edit')
            self.assertEqual(output.status_code, 200)
            self.assertTrue('<strong>Edit tag: tag1</strong>' in output.data)

            csrf_token = self.get_csrf(output=output)

            data = {'tag': 'tag2',
                    'tag_description': 'lorem ipsum',
                    'tag_color': 'DeepSkyBlue'}

            output = self.app.post('/test/tag/tag1/edit', data=data)
            self.assertEqual(output.status_code, 200)
            self.assertTrue('<strong>Edit tag: tag1</strong>' in output.data)

            data['csrf_token'] = csrf_token
            output = self.app.post(
                '/test/tag/tag1/edit', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                'Settings - test - Pagure', output.data)
            self.assertIn(
                '</button>\n                      '
                'Edited tag: tag1()[DeepSkyBlue] to tag2(lorem ipsum)[DeepSkyBlue]',
                output.data)

            # update tag with empty description
            data['tag_description'] = ''
            output = self.app.post(
                '/test/tag/tag2/edit', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                'Settings - test - Pagure', output.data)
            self.assertIn(
                '</button>\n                      '
                'Edited tag: tag2(lorem ipsum)[DeepSkyBlue] to tag2()[DeepSkyBlue]',
                output.data)

        # After edit, list tags
        tags = pagure.lib.get_tags_of_project(self.session, repo)
        self.assertEqual([tag.tag for tag in tags], ['tag2'])

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_remove_tag(self, p_send_email, p_ugt):
        """ Test the remove_tag endpoint. """
        p_send_email.return_value = True
        p_ugt.return_value = True

        # No Git repo
        output = self.app.post('/foo/droptag/')
        self.assertEqual(output.status_code, 404)

        user = tests.FakeUser()
        with tests.user_set(pagure.APP, user):
            output = self.app.post('/foo/droptag/')
            self.assertEqual(output.status_code, 404)

            tests.create_projects(self.session)
            tests.create_projects_git(os.path.join(self.path, 'repos'))

            output = self.app.post('/test/droptag/')
            self.assertEqual(output.status_code, 403)

        # User not logged in
        output = self.app.post('/test/droptag/')
        self.assertEqual(output.status_code, 302)

        # Create issues to play with
        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue',
            content='We should work on this',
            user='pingou',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue')

        # Add a tag to the issue
        issue = pagure.lib.search_issues(self.session, repo, issueid=1)
        msg = pagure.lib.add_tag_obj(
            session=self.session,
            obj=issue,
            tags='tag1',
            user='pingou',
            gitfolder=None)
        self.session.commit()
        self.assertEqual(msg, 'Issue tagged with: tag1')

        # Before edit, list tags
        tags = pagure.lib.get_tags_of_project(self.session, repo)
        self.assertEqual([tag.tag for tag in tags], ['tag1'])

        # Edit tag
        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            output = self.app.post(
                '/test/droptag/', data={}, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertTrue(
                '<title>Settings - test - Pagure</title>' in output.data)
            self.assertTrue("<h3>Settings for test</h3>" in output.data)

            csrf_token = self.get_csrf(output=output)

            data = {'tag': 'tag1'}

            output = self.app.post(
                '/test/droptag/', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertTrue("<h3>Settings for test</h3>" in output.data)

            data['csrf_token'] = csrf_token
            output = self.app.post(
                '/test/droptag/', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertTrue("<h3>Settings for test</h3>" in output.data)
            self.assertIn(
                '</button>\n                      '
                'Issue **un**tagged with: tag1', output.data)

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_delete_issue(self, p_send_email, p_ugt):
        """ Test the delete_issue endpoint. """
        p_send_email.return_value = True
        p_ugt.return_value = True

        tests.create_projects(self.session)
        tests.create_projects_git(os.path.join(self.path, 'repos'))
        tests.create_projects_git(os.path.join(self.path, 'tickets'))

        # Create issues to play with
        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue',
            content='We should work on this',
            user='pingou',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue')

        user = tests.FakeUser()
        with tests.user_set(pagure.APP, user):
            output = self.app.post(
                '/foo/issue/1/drop', follow_redirects=True)
            self.assertEqual(output.status_code, 404)

            output = self.app.post(
                '/test/issue/100/drop', follow_redirects=True)
            self.assertEqual(output.status_code, 404)

            output = self.app.post(
                '/test/issue/1/drop', follow_redirects=True)
            self.assertEqual(output.status_code, 403)

        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            output = self.app.post(
                '/test/issue/1/drop', follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)

            csrf_token = self.get_csrf(output=output)

            data = {
            }

            # No CSRF token
            output = self.app.post(
                '/test/issue/1/drop', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)

            data['csrf_token'] = csrf_token
            output = self.app.post(
                '/test/issue/1/drop', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issues - test - Pagure</title>', output.data)
            self.assertIn(
                '</button>\n                      Issue deleted',
                output.data)

        # Project w/o issue tracker
        repo = pagure.get_authorized_project(self.session, 'test')
        repo.settings = {'issue_tracker': False}
        self.session.add(repo)
        self.session.commit()

        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            output = self.app.post('/test/issue/1/drop', data=data)
            self.assertEqual(output.status_code, 404)

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_update_issue_edit_comment(self,  p_send_email, p_ugt):
        """ Test the issues edit comment endpoint """
        p_send_email.return_value = True
        p_ugt.return_value = True

        tests.create_projects(self.session)
        tests.create_projects_git(
            os.path.join(self.path, 'repos'), bare=True)

        # Create issues to play with
        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue',
            content='We should work on this',
            user='pingou',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue')

        user = tests.FakeUser()
        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test/issue/1')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)

            csrf_token = self.get_csrf(output=output)

            # Add new comment
            data = {
                'csrf_token': csrf_token,
                'comment': 'Woohoo a second comment!',
            }
            output = self.app.post(
                '/test/issue/1/update', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)
            self.assertIn(
                '</button>\n                      Comment added',
                output.data)
            self.assertTrue(
                '<p>Woohoo a second comment!</p>' in output.data)
            self.assertEqual(output.data.count('comment_body">'), 2)

        repo = pagure.get_authorized_project(self.session, 'test')
        issue = pagure.lib.search_issues(self.session, repo, issueid=1)
        self.assertEqual(len(issue.comments), 1)
        self.assertEqual(
            issue.comments[0].comment,
            'Woohoo a second comment!')

        data = {
            'csrf_token': csrf_token,
            'edit_comment': 1,
            'update_comment': 'Updated comment',
        }

        user = tests.FakeUser()
        with tests.user_set(pagure.APP, user):
            # Wrong issue id
            output = self.app.post(
                '/test/issue/3/update', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 404)

            # Wrong user
            output = self.app.post(
                '/test/issue/1/update', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 403)

        user = tests.FakeUser()
        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            # Edit comment
            output = self.app.post(
                '/test/issue/1/update', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)
            self.assertIn(
                '</button>\n                      Comment updated',
                output.data)

        repo = pagure.get_authorized_project(self.session, 'test')
        issue = pagure.lib.search_issues(self.session, repo, issueid=1)
        self.assertEqual(len(issue.comments), 1)
        self.assertEqual(issue.comments[0].comment, 'Updated comment')

        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test/issue/1/comment/1/edit')
            self.assertIn(
                '<title>test - Pagure</title>', output.data)
            self.assertTrue('<div id="edit">' in output.data)
            self.assertTrue('<section class="edit_comment">' in output.data)
            self.assertTrue(
                '<textarea class="form-control" id="update_comment"'
                in output.data)

            csrf_token = self.get_csrf(output=output)

            data['csrf_token'] = csrf_token
            data['update_comment'] = 'Second update'

            # Edit the comment with the other endpoint
            output = self.app.post(
                '/test/issue/1/comment/1/edit',
                data=data,
                follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)
            self.assertIn(
                '</button>\n                      Comment updated',
                output.data)

        repo = pagure.get_authorized_project(self.session, 'test')
        issue = pagure.lib.search_issues(self.session, repo, issueid=1)
        self.assertEqual(len(issue.comments), 1)
        self.assertEqual(issue.comments[0].comment, 'Second update')

        # Create another issue from someone else
        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue',
            content='We should work on this',
            user='foo',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue')

        issue = pagure.lib.search_issues(self.session, repo, issueid=1)
        self.assertEqual(len(issue.comments), 1)
        self.assertEqual(issue.status, 'Open')

        issue = pagure.lib.search_issues(self.session, repo, issueid=2)
        self.assertEqual(len(issue.comments), 0)
        self.assertEqual(issue.status, 'Open')

        user = tests.FakeUser(username='foo')
        with tests.user_set(pagure.APP, user):
            data = {
                'csrf_token': csrf_token,
                'comment': 'Nevermind figured it out',
                'status': 'Closed',
                'close_status': 'Invalid'
            }

            # Add a comment and close the ticket #1
            output = self.app.post(
                '/test/issue/1/update', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertNotIn(
                '</button>\n                      '
                'Successfully edited issue #1\n',
                output.data
            )
            self.assertIn(
                '</button>\n                      Comment added\n',
                output.data
            )
            self.assertNotIn(
                'editmetadatatoggle">\n              Edit Metadata',
                output.data
            )

            data = {
                'csrf_token': csrf_token,
                'comment': 'Nevermind figured it out',
                'status': 'Closed',
                'close_status': 'Invalid'
            }

            # Add a comment and close the ticket #2
            output = self.app.post(
                '/test/issue/2/update', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '</button>\n                      '
                'Issue close_status updated to: Invalid\n',
                output.data
            )
            self.assertIn(
                '</button>\n                      Comment added\n',
                output.data
            )
            self.assertIn(
                '</button>\n                      '
                'Issue status updated to: Closed (was: Open)\n',
                output.data
            )
            self.assertIn(
                'editmetadatatoggle">\n              Edit Metadata',
                output.data
            )

        # Ticket #1 has one more comment and is still open
        issue = pagure.lib.search_issues(self.session, repo, issueid=1)
        self.assertEqual(len(issue.comments), 2)
        self.assertEqual(issue.status, 'Open')

        # Ticket #2 has one less comment and is closed
        issue = pagure.lib.search_issues(self.session, repo, issueid=2)
        self.assertEqual(len(issue.comments), 2)
        self.assertEqual(
            issue.comments[0].comment,
            'Nevermind figured it out')
        self.assertEqual(
            issue.comments[1].comment,
            '**Metadata Update from @foo**:\n'
            '- Issue close_status updated to: Invalid\n'
            '- Issue status updated to: Closed (was: Open)')
        self.assertEqual(issue.status, 'Closed')

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_git_urls(self, p_send_email, p_ugt):
        """ Check that the url to the git repo for issues is present/absent when
        it should.
        """
        p_send_email.return_value = True
        p_ugt.return_value = True

        self.test_view_issues()

        user = tests.FakeUser()
        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            # Check that the git issue URL is present
            output = self.app.get('/test')
            self.assertNotIn(
                '<h5><strong>Issues GIT URLs</strong></h5>', output.data)

            # Project w/o issue tracker
            repo = pagure.get_authorized_project(self.session, 'test')
            repo.settings = {'issue_tracker': True}
            self.session.add(repo)
            self.session.commit()

            # Check that the git issue URL is gone
            output = self.app.get('/test')
            self.assertIn(
                '<h5><strong>Issues GIT URLs</strong></h5>', output.data)

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_update_tags(self, p_send_email, p_ugt):
        """ Test the update_tags endpoint. """
        p_send_email.return_value = True
        p_ugt.return_value = True

        # No Git repo
        output = self.app.post('/foo/update/tags')
        self.assertEqual(output.status_code, 404)

        user = tests.FakeUser()
        with tests.user_set(pagure.APP, user):
            output = self.app.post('/foo/update/tags')
            self.assertEqual(output.status_code, 404)

            tests.create_projects(self.session)
            tests.create_projects_git(os.path.join(self.path, 'repos'))

            output = self.app.post('/test/update/tags')
            self.assertEqual(output.status_code, 403)

        # User not logged in
        output = self.app.post('/test/update/tags')
        self.assertEqual(output.status_code, 302)

        # Create issues to play with
        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue',
            content='We should work on this',
            user='pingou',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue')

         # Before update, list tags
        tags = pagure.lib.get_tags_of_project(self.session, repo)
        self.assertEqual([tag.tag for tag in tags], [])

        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            # No CSRF
            data = {
                'tag': 'red',
                'tag_description': 'lorem ipsum',
                'tag_color': '#ff0000'
            }
            output = self.app.post(
                '/test/update/tags', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Settings - test - Pagure</title>', output.data)
            self.assertIn(
                '        <ul class="list-group list-group-flush">'
                '\n        </ul>', output.data)

            csrf_token = self.get_csrf(output=output)

            # Invalid color
            data = {
                'tag': 'red',
                'tag_description': 'lorem ipsum',
                'tag_color': 'red',
                'csrf_token': csrf_token,
            }
            output = self.app.post(
                '/test/update/tags', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Settings - test - Pagure</title>', output.data)
            self.assertIn(
                '</button>\n                      '
                'Color: red does not match the expected pattern',
                output.data)
            self.assertIn(
                '        <ul class="list-group list-group-flush">'
                '\n        </ul>', output.data)

            # Inconsistent length tags (missing tag field)
            data = {
                'tag': 'red',
                'tag_description': ['lorem ipsum', 'foo bar'],
                'tag_color': ['#ff0000', '#003cff'],
                'csrf_token': csrf_token,
            }
            output = self.app.post(
                '/test/update/tags', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Settings - test - Pagure</title>', output.data)
            self.assertIn(
                '</button>\n                      Error: Incomplete request. '
                'One or more tag fields missing.', output.data)
            self.assertIn(
                '        <ul class="list-group list-group-flush">'
                '\n        </ul>', output.data)

            # Inconsistent length color
            data = {
                'tag': ['red', 'blue'],
                'tag_description': ['lorem ipsum', 'foo bar'],
                'tag_color': 'red',
                'csrf_token': csrf_token,
            }
            output = self.app.post(
                '/test/update/tags', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Settings - test - Pagure</title>', output.data)
            self.assertIn(
                '</button>\n                      '
                'Color: red does not match the expected pattern',
                output.data)
            self.assertIn(
                '</button>\n                      Error: Incomplete request. '
                'One or more tag color fields missing.', output.data)
            self.assertIn(
                '        <ul class="list-group list-group-flush">'
                '\n        </ul>', output.data)

            # Inconsistent length description
            data = {
                'tag': ['red', 'blue'],
                'tag_description': 'lorem ipsum',
                'tag_color': ['#ff0000', '#003cff'],
                'csrf_token': csrf_token,
            }
            output = self.app.post(
                '/test/update/tags', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Settings - test - Pagure</title>', output.data)
            self.assertIn(
                '</button>\n                      Error: Incomplete request. '
                'One or more tag description fields missing.', output.data)
            self.assertIn(
                '        <ul class="list-group list-group-flush">'
                '\n        </ul>', output.data)

            # consistent length, but empty description
            data = {
                'tag': ['red', 'blue'],
                'tag_description': ['lorem ipsum', ''],
                'tag_color': ['#ff0000', '#003cff'],
                'csrf_token': csrf_token,
            }
            output = self.app.post(
                '/test/update/tags', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Settings - test - Pagure</title>', output.data)
            self.assertIn(
                '<span class="label label-info" style="background-color:'
                '#003cff">blue</span>\n'
                '            &nbsp;<span class="text-muted">'
                '</span>', output.data)
            self.assertIn(
                '<input type="hidden" value="blue" name="tag" />',
                output.data)
            self.assertIn(
                '<span class="label label-info" style="background-color:'
                '#ff0000">red</span>\n'
                '            &nbsp;<span class="text-muted">lorem ipsum'
                '</span>', output.data)
            self.assertIn(
                '<input type="hidden" value="red" name="tag" />',
                output.data)

            # Valid query
            data = {
                'tag': ['red', 'green'],
                'tag_description': ['lorem ipsum', 'sample description'],
                'tag_color': ['#ff0000', '#00ff00'],
                'csrf_token': csrf_token,
            }
            output = self.app.post(
                '/test/update/tags', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Settings - test - Pagure</title>', output.data)
            self.assertIn(
                '<span class="label label-info" style="background-color:'
                '#00ff00">green</span>\n'
                '            &nbsp;<span class="text-muted">sample description'
                '</span>', output.data)
            self.assertIn(
                '<input type="hidden" value="green" name="tag" />',
                output.data)
            self.assertIn(
                '<span class="label label-info" style="background-color:'
                '#ff0000">red</span>\n'
                '            &nbsp;<span class="text-muted">lorem ipsum'
                '</span>', output.data)
            self.assertIn(
                '<input type="hidden" value="red" name="tag" />',
                output.data)

        # After update, list tags
        tags = pagure.lib.get_tags_of_project(self.session, repo)
        self.assertEqual([tag.tag for tag in tags], ['blue', 'green', 'red'])

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_view_issue_namespace_comment(self, p_send_email, p_ugt):
        """ Test comment on the view_issue endpoint on namespaced project.
        """
        # Create the project ns/test
        item = pagure.lib.model.Project(
            user_id=1,  # pingou
            name='test3',
            namespace='ns',
            description='test project #3',
            hook_token='aaabbbcccdd',
        )
        self.session.add(item)
        self.session.commit()
        self.assertEqual(item.fullname, 'ns/test3')
        pygit2.init_repository(
            os.path.join(self.path, 'repos', 'ns', 'test3.git'),
            bare=True)

        # Create 2 issues
        iss = pagure.lib.new_issue(
            issue_id=1,
            session=self.session,
            repo=item,
            title='test issue',
            content='content test issue',
            user='pingou',
            ticketfolder=None,
        )
        self.session.commit()
        self.assertEqual(iss.id, 1)
        self.assertEqual(iss.title, 'test issue')
        self.assertEqual(iss.project.fullname, 'ns/test3')

        iss = pagure.lib.new_issue(
            issue_id=2,
            session=self.session,
            repo=item,
            title='test issue2',
            content='content test issue2',
            user='pingou',
            ticketfolder=None,
        )
        self.session.commit()
        self.assertEqual(iss.id, 2)
        self.assertEqual(iss.title, 'test issue2')
        self.assertEqual(iss.project.fullname, 'ns/test3')

        # Add a comment on the second issue pointing to the first one
        issue_comment = pagure.lib.model.IssueComment(
            issue_uid=iss.uid,
            comment='foo bar #1 see?',
            user_id=1,  # pingou
            notification=False,
        )
        self.session.add(issue_comment)
        self.session.commit()

        output = self.app.get('/ns/test3/issue/2')
        self.assertEqual(output.status_code, 200)
        self.assertIn(
            '<span class="comment_text comment_body">'
            '<p>foo bar<a href="/ns/test3/issue/1" '
            'title="[Open] test issue"> #1</a> see?</p></span>', output.data)

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_view_issue_forked_namespace_comment(self, p_send_email, p_ugt):
        """ Test comment on the view_issue endpoint on namespaced project.
        """
        # Create the project ns/test
        item = pagure.lib.model.Project(
            user_id=1,  # pingou
            name='test3',
            namespace='ns',
            description='test project #3',
            hook_token='aaabbbcccdd',
        )
        self.session.add(item)
        self.session.commit()
        self.assertEqual(item.fullname, 'ns/test3')

        # Fork the project ns/test
        item = pagure.lib.model.Project(
            user_id=1,  # pingou
            parent_id=1,  # ns/test
            is_fork=True,
            name='test3',
            namespace='ns',
            description='test project #3',
            hook_token='aaabbbcccddff',
        )
        self.session.add(item)
        self.session.commit()
        self.assertEqual(item.fullname, 'forks/pingou/ns/test3')

        pygit2.init_repository(
            os.path.join(
                self.path, 'repos', 'forks', 'pingou', 'ns', 'test3.git'),
            bare=True)

        # Create 2 issues
        iss = pagure.lib.new_issue(
            issue_id=1,
            session=self.session,
            repo=item,
            title='test issue',
            content='content test issue',
            user='pingou',
            ticketfolder=None,
        )
        self.session.commit()
        self.assertEqual(iss.id, 1)
        self.assertEqual(iss.title, 'test issue')
        self.assertEqual(iss.project.fullname, 'forks/pingou/ns/test3')

        iss = pagure.lib.new_issue(
            issue_id=2,
            session=self.session,
            repo=item,
            title='test issue2',
            content='content test issue2',
            user='pingou',
            ticketfolder=None,
        )
        self.session.commit()
        self.assertEqual(iss.id, 2)
        self.assertEqual(iss.title, 'test issue2')
        self.assertEqual(iss.project.fullname, 'forks/pingou/ns/test3')

        # Add a comment on the second issue pointing to the first one
        issue_comment = pagure.lib.model.IssueComment(
            issue_uid=iss.uid,
            comment='foo bar #1 see?',
            user_id=1,  # pingou
            notification=False,
        )
        self.session.add(issue_comment)
        self.session.commit()

        output = self.app.get('/fork/pingou/ns/test3/issue/2')
        self.assertEqual(output.status_code, 200)
        self.assertIn(
            '<span class="comment_text comment_body">'
            '<p>foo bar<a href="/fork/pingou/ns/test3/issue/1" '
            'title="[Open] test issue"> #1</a> see?</p></span>', output.data)

    @patch('pagure.lib.git.update_git')
    @patch('pagure.lib.notify.send_email')
    def test_view_issue_closed(self, p_send_email, p_ugt):
        """ Test viewing a closed issue. """
        p_send_email.return_value = True
        p_ugt.return_value = True

        tests.create_projects(self.session)
        tests.create_projects_git(
            os.path.join(self.path, 'repos'), bare=True)

        # Create issues to play with
        repo = pagure.get_authorized_project(self.session, 'test')
        msg = pagure.lib.new_issue(
            session=self.session,
            repo=repo,
            title='Test issue',
            content='We should work on this',
            user='pingou',
            ticketfolder=None
        )
        self.session.commit()
        self.assertEqual(msg.title, 'Test issue')

        user = tests.FakeUser()
        user.username = 'pingou'
        with tests.user_set(pagure.APP, user):
            output = self.app.get('/test/issue/1')
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)

            csrf_token = self.get_csrf(output=output)

            # Add new comment
            data = {
                'csrf_token': csrf_token,
                'status': 'Closed',
                'close_status': 'Fixed',
                'comment': 'Woohoo a second comment!',
            }
            output = self.app.post(
                '/test/issue/1/update', data=data, follow_redirects=True)
            self.assertEqual(output.status_code, 200)
            self.assertIn(
                '<title>Issue #1: Test issue - test - Pagure</title>',
                output.data)
            self.assertIn(
                '<a class="btn btn-primary btn-sm" '
                'href="/test/issue/1/edit" title="Edit this issue">',
                output.data)
            self.assertIn(
                '</button>\n                      Comment added',
                output.data)
            self.assertTrue(
                '<p>Woohoo a second comment!</p>' in output.data)
            self.assertEqual(output.data.count('comment_body">'), 2)
            self.assertTrue(
                '<option selected value="Fixed">Fixed</option>'
                in output.data)
            self.assertEqual(
                output.data.count(
                'title="Reply to this comment - lose formatting">',
                ), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
