# -*- coding: utf-8 -*-

"""
 (c) 2017 - Copyright Red Hat Inc

 Authors:
   Pierre-Yves Chibon <pingou@pingoured.fr>

"""

import unittest
import sys
import os

import pygit2

sys.path.insert(0, os.path.join(os.path.dirname(
    os.path.abspath(__file__)), '..'))

import pagure
import pagure.lib
import tests


class ViewCommitFlagtests(tests.SimplePagureTest):
    """ Tests for the UI related to commit flags """

    def setUp(self):
        """ Set up the environnment, ran before every tests. """
        super(ViewCommitFlagtests, self).setUp()

        pagure.APP.config['TESTING'] = True
        pagure.SESSION = self.session
        pagure.ui.SESSION = self.session
        pagure.ui.app.SESSION = self.session
        pagure.ui.filters.SESSION = self.session
        pagure.ui.repo.SESSION = self.session

        tests.create_projects(self.session)
        tests.create_tokens(self.session)

        # Add a README to the git repo - First commit
        tests.add_readme_git_repo(os.path.join(self.path, 'repos', 'test.git'))
        repo = pygit2.Repository(os.path.join(self.path, 'repos', 'test.git'))
        self.commit = repo.revparse_single('HEAD')

    def test_view_commit_no_flag(self):
        """ Test the view_commit endpoint. """

        # View first commit
        output = self.app.get('/test/c/%s' % self.commit.oid.hex)
        self.assertEqual(output.status_code, 200)
        self.assertIn(
            '<title>Commit - test - %s - Pagure</title>' % self.commit.oid.hex,
            output.data)
        self.assertIn(
            '<div class="list-group" id="diff_list" style="display:none;">',
            output.data)
        self.assertIn('  Merged by Alice Author\n', output.data)
        self.assertIn('  Committed by Cecil Committer\n', output.data)
        self.assertIn('''<section class="list-group" id="flag_list">
  <div class="card" id="pr_flags">
      <ul class="list-group list-group-flush">
      </ul>
    </div>
</section>''', output.data)

    def test_view_commit_pending_flag(self):
        """ Test the view_commit endpoint with a pending flag. """
        repo = pagure.get_authorized_project(self.session, 'test')

        msg = pagure.lib.add_commit_flag(
            session=self.session,
            repo=repo,
            commit_hash=self.commit.oid.hex,
            username='simple-koji-ci',
            status='pending',
            percent=None,
            comment='Build is running',
            url='https://koji.fp.o/koji...',
            uid='uid',
            user='foo',
            token='aaabbbcccddd'
        )
        self.assertEqual(msg, ('Flag added', 'uid'))

        # View first commit
        output = self.app.get('/test/c/%s' % self.commit.oid.hex)
        self.assertEqual(output.status_code, 200)
        self.assertIn(
            '<title>Commit - test - %s - Pagure</title>' % self.commit.oid.hex,
            output.data)
        self.assertIn(
            '<div class="list-group" id="diff_list" style="display:none;">',
            output.data)
        self.assertIn('  Merged by Alice Author\n', output.data)
        self.assertIn('  Committed by Cecil Committer\n', output.data)
        self.assertIn(
            '<span>\n                <a href="https://koji.fp.o/koji...">'
            'simple-koji-ci</a>\n              </span>', output.data)
        self.assertIn(
            '<div class="pull-xs-right">\n                '
            '<span class="label label-info">pending'
            '</span>\n              </div>', output.data)
        self.assertIn(
            '<span>Build is running</span>', output.data)

    def test_view_commit_success_flag(self):
        """ Test the view_commit endpoint with a successful flag. """
        repo = pagure.get_authorized_project(self.session, 'test')

        msg = pagure.lib.add_commit_flag(
            session=self.session,
            repo=repo,
            commit_hash=self.commit.oid.hex,
            username='simple-koji-ci',
            status='success',
            percent=100,
            comment='Build passed',
            url='https://koji.fp.o/koji...',
            uid='uid',
            user='foo',
            token='aaabbbcccddd'
        )
        self.assertEqual(msg, ('Flag added', 'uid'))

        # View first commit
        output = self.app.get('/test/c/%s' % self.commit.oid.hex)
        self.assertEqual(output.status_code, 200)
        self.assertIn(
            '<title>Commit - test - %s - Pagure</title>' % self.commit.oid.hex,
            output.data)
        self.assertIn(
            '<div class="list-group" id="diff_list" style="display:none;">',
            output.data)
        self.assertIn('  Merged by Alice Author\n', output.data)
        self.assertIn('  Committed by Cecil Committer\n', output.data)
        self.assertIn(
            '<span>\n                <a href="https://koji.fp.o/koji...">'
            'simple-koji-ci</a>\n              </span>', output.data)
        self.assertIn(
            '<div class="pull-xs-right">\n                '
            '<span class="label label-success">success (100%)'
            '</span>\n              </div>', output.data)
        self.assertIn(
            '<span>Build passed</span>', output.data)

    def test_view_commit_error_flag(self):
        """ Test the view_commit endpoint with a error flag. """
        repo = pagure.get_authorized_project(self.session, 'test')

        msg = pagure.lib.add_commit_flag(
            session=self.session,
            repo=repo,
            commit_hash=self.commit.oid.hex,
            username='simple-koji-ci',
            status='error',
            percent=None,
            comment='Build errored',
            url='https://koji.fp.o/koji...',
            uid='uid',
            user='foo',
            token='aaabbbcccddd'
        )
        self.assertEqual(msg, ('Flag added', 'uid'))

        # View first commit
        output = self.app.get('/test/c/%s' % self.commit.oid.hex)
        self.assertEqual(output.status_code, 200)
        self.assertIn(
            '<title>Commit - test - %s - Pagure</title>' % self.commit.oid.hex,
            output.data)
        self.assertIn(
            '<div class="list-group" id="diff_list" style="display:none;">',
            output.data)
        self.assertIn('  Merged by Alice Author\n', output.data)
        self.assertIn('  Committed by Cecil Committer\n', output.data)
        self.assertIn(
            '<span>\n                <a href="https://koji.fp.o/koji...">'
            'simple-koji-ci</a>\n              </span>', output.data)
        self.assertIn(
            '<div class="pull-xs-right">\n                '
            '<span class="label label-danger">error'
            '</span>\n              </div>', output.data)
        self.assertIn(
            '<span>Build errored</span>', output.data)

    def test_view_commit_failure_flag(self):
        """ Test the view_commit endpoint with a failure flag. """
        repo = pagure.get_authorized_project(self.session, 'test')

        msg = pagure.lib.add_commit_flag(
            session=self.session,
            repo=repo,
            commit_hash=self.commit.oid.hex,
            username='simple-koji-ci',
            status='failure',
            percent=None,
            comment='Build failed',
            url='https://koji.fp.o/koji...',
            uid='uid',
            user='foo',
            token='aaabbbcccddd'
        )
        self.assertEqual(msg, ('Flag added', 'uid'))

        # View first commit
        output = self.app.get('/test/c/%s' % self.commit.oid.hex)
        self.assertEqual(output.status_code, 200)
        self.assertIn(
            '<title>Commit - test - %s - Pagure</title>' % self.commit.oid.hex,
            output.data)
        self.assertIn(
            '<div class="list-group" id="diff_list" style="display:none;">',
            output.data)
        self.assertIn('  Merged by Alice Author\n', output.data)
        self.assertIn('  Committed by Cecil Committer\n', output.data)
        self.assertIn(
            '<span>\n                <a href="https://koji.fp.o/koji...">'
            'simple-koji-ci</a>\n              </span>', output.data)
        self.assertIn(
            '<div class="pull-xs-right">\n                '
            '<span class="label label-danger">failure'
            '</span>\n              </div>', output.data)
        self.assertIn(
            '<span>Build failed</span>', output.data)

    def test_view_commit_canceled_flag(self):
        """ Test the view_commit endpoint with a canceled flag. """
        repo = pagure.get_authorized_project(self.session, 'test')

        msg = pagure.lib.add_commit_flag(
            session=self.session,
            repo=repo,
            commit_hash=self.commit.oid.hex,
            username='simple-koji-ci',
            status='canceled',
            percent=None,
            comment='Build canceled',
            url='https://koji.fp.o/koji...',
            uid='uid',
            user='foo',
            token='aaabbbcccddd'
        )
        self.assertEqual(msg, ('Flag added', 'uid'))

        # View first commit
        output = self.app.get('/test/c/%s' % self.commit.oid.hex)
        self.assertEqual(output.status_code, 200)
        self.assertIn(
            '<title>Commit - test - %s - Pagure</title>' % self.commit.oid.hex,
            output.data)
        self.assertIn(
            '<div class="list-group" id="diff_list" style="display:none;">',
            output.data)
        self.assertIn('  Merged by Alice Author\n', output.data)
        self.assertIn('  Committed by Cecil Committer\n', output.data)
        self.assertIn(
            '<span>\n                <a href="https://koji.fp.o/koji...">'
            'simple-koji-ci</a>\n              </span>', output.data)
        self.assertIn(
            '<div class="pull-xs-right">\n                '
            '<span class="label label-warning">canceled'
            '</span>\n              </div>', output.data)
        self.assertIn(
            '<span>Build canceled</span>', output.data)


if __name__ == '__main__':
    unittest.main(verbosity=2)
