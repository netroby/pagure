# -*- coding: utf-8 -*-

"""
 (c) 2017 - Copyright Red Hat Inc

 Authors:
   Pierre-Yves Chibon <pingou@pingoured.fr>

"""

__requires__ = ['SQLAlchemy >= 0.8']
import pkg_resources  # noqa

import json  # noqa
import unittest  # noqa
import shutil  # noqa
import sys  # noqa
import tempfile  # noqa
import time  # noqa
import os  # noqa

import pygit2  # noqa
from mock import patch, MagicMock  # noqa

sys.path.insert(0, os.path.join(os.path.dirname(
    os.path.abspath(__file__)), '..'))

import pagure.lib  # noqa
import tests  # noqa
from pagure.lib.repo import PagureRepo  # noqa


class PagureFlaskForkPrtests(tests.Modeltests):
    """ Tests for flask fork controller of pagure regarding diffing PRs """

    @patch('pagure.lib.notify.send_email', MagicMock(return_value=True))
    def setUp(self):
        """ Set up the environnment, ran before every tests. """
        super(PagureFlaskForkPrtests, self).setUp()

        # Create the main project in the DB
        item = pagure.lib.model.Project(
            user_id=1,  # pingou
            name='test',
            description='test project #1',
            hook_token='aaabbbccc',
        )
        item.close_status = [
            'Invalid', 'Insufficient data', 'Fixed', 'Duplicate']
        self.session.add(item)
        self.session.commit()

        # Create the fork
        item = pagure.lib.model.Project(
            user_id=1,  # pingou
            name='test',
            description='test project #1',
            hook_token='aaabbbcccdd',
            parent_id=1,
            is_fork=True,
        )
        item.close_status = [
            'Invalid', 'Insufficient data', 'Fixed', 'Duplicate']
        self.session.add(item)
        self.session.commit()

        # Create two git repos, one has 6 commits, the other 4 of which only
        # 1 isn't present in the first repo
        gitrepo = os.path.join(self.path, 'repos', 'test.git')
        pygit2.init_repository(gitrepo, bare=True)

        gitrepo2 = os.path.join(
            self.path, 'repos', 'forks', 'pingou', 'test.git')
        pygit2.init_repository(gitrepo2, bare=True)

        newpath = tempfile.mkdtemp(prefix='pagure-fork-test')
        repopath = os.path.join(newpath, 'test')
        clone_repo = pygit2.clone_repository(gitrepo, repopath)

        # Do 3 commits to the main repo
        for i in range(3):
            with open(os.path.join(repopath, 'sources'), 'w') as stream:
                stream.write('foo%s\n bar%s\n' % (i, i))
            clone_repo.index.add('sources')
            clone_repo.index.write()

            parents = []
            try:
                last_commit = clone_repo.revparse_single('HEAD')
                parents = [last_commit.oid.hex]
            except KeyError:
                pass

            # Commits the files added
            tree = clone_repo.index.write_tree()
            author = pygit2.Signature(
                'Alice Author', 'alice@authors.tld')
            committer = pygit2.Signature(
                'Cecil Committer', 'cecil@committers.tld')
            clone_repo.create_commit(
                'refs/heads/master',  # the name of the reference to update
                author,
                committer,
                'Editing the file sources for testing #%s' % i,
                # binary string representing the tree object ID
                tree,
                # list of binary strings representing parents of the new commit
                parents
            )

        # Push to the main repo
        refname = 'refs/heads/master:refs/heads/master'
        ori_remote = clone_repo.remotes[0]
        PagureRepo.push(ori_remote, refname)

        # Push to the fork repo
        remote = clone_repo.create_remote('pingou_fork', gitrepo2)
        PagureRepo.push(remote, refname)

        # Do another 3 commits to the main repo
        for i in range(3, 6):
            with open(os.path.join(repopath, 'sources'), 'w') as stream:
                stream.write('foo%s\n bar%s\n' % (i, i))
            clone_repo.index.add('sources')
            clone_repo.index.write()

            last_commit = clone_repo.revparse_single('HEAD')

            # Commits the files added
            tree = clone_repo.index.write_tree()
            author = pygit2.Signature(
                'Alice Author', 'alice@authors.tld')
            committer = pygit2.Signature(
                'Cecil Committer', 'cecil@committers.tld')
            clone_repo.create_commit(
                'refs/heads/master',  # the name of the reference to update
                author,
                committer,
                'Editing the file sources for testing #%s' % i,
                # binary string representing the tree object ID
                tree,
                # list of binary strings representing parents of the new commit
                [last_commit.oid.hex]
            )
        # Push to the main repo
        refname = 'refs/heads/master:refs/heads/master'
        ori_remote = clone_repo.remotes[0]
        PagureRepo.push(ori_remote, refname)

        # Add two commits to the fork repo
        repopath = os.path.join(newpath, 'pingou_test')
        clone_repo = pygit2.clone_repository(gitrepo2, repopath)

        with open(os.path.join(repopath, 'sources'), 'w') as stream:
                stream.write('foo\n bar\n')
        clone_repo.index.add('sources')
        clone_repo.index.write()

        last_commit = clone_repo.revparse_single('HEAD')

        # Commits the files added
        tree = clone_repo.index.write_tree()
        author = pygit2.Signature(
            'Alice Author', 'alice@authors.tld')
        committer = pygit2.Signature(
            'Cecil Committer', 'cecil@committers.tld')
        last_commit = clone_repo.create_commit(
            'refs/heads/feature_foo',  # the name of the reference to update
            author,
            committer,
            'New edition on side branch of the file sources for testing',
            # binary string representing the tree object ID
            tree,
            # list of binary strings representing parents of the new commit
            [last_commit.oid.hex]
        )

        with open(os.path.join(repopath, 'sources'), 'w') as stream:
                stream.write('foo\n bar\nbaz\n')
        clone_repo.index.add('sources')
        clone_repo.index.write()

        # Commits the files added
        tree = clone_repo.index.write_tree()
        author = pygit2.Signature(
            'Alice Author', 'alice@authors.tld')
        committer = pygit2.Signature(
            'Cecil Committer', 'cecil@committers.tld')
        last_commit = clone_repo.create_commit(
            'refs/heads/feature_foo',  # the name of the reference to update
            author,
            committer,
            'Second edit on side branch of the file sources for testing',
            # binary string representing the tree object ID
            tree,
            # list of binary strings representing parents of the new commit
            [last_commit.hex]
        )

        # Push to the fork repo
        ori_remote = clone_repo.remotes[0]
        refname = 'refs/heads/feature_foo:refs/heads/feature_foo'
        PagureRepo.push(ori_remote, refname)

        shutil.rmtree(newpath)

        # Create the PR between the two repos
        repo = pagure.get_authorized_project(self.session, 'test')
        forked_repo = pagure.get_authorized_project(
            self.session, 'test', user='pingou')

        req = pagure.lib.new_pull_request(
            session=self.session,
            repo_from=forked_repo,
            branch_from='feature_foo',
            repo_to=repo,
            branch_to='master',
            title='test pull-request',
            user='pingou',
            requestfolder=None,
        )
        self.assertEqual(req.id, 1)
        self.assertEqual(req.title, 'test pull-request')

    def test_get_pr_info(self):
        """ Test pagure.ui.fork._get_pr_info """

        gitrepo = os.path.join(self.path, 'repos', 'test.git')
        gitrepo2 = os.path.join(
            self.path, 'repos', 'forks', 'pingou', 'test.git')

        diff, diff_commits, orig_commit = pagure.lib.git.get_diff_info(
            repo_obj=PagureRepo(gitrepo2),
            orig_repo=PagureRepo(gitrepo),
            branch_from='feature_foo',
            branch_to='master'
        )
        self.assertEqual(len(diff_commits), 2)
        self.assertEqual(
            diff_commits[0].message,
            'Second edit on side branch of the file sources for testing'
        )
        self.assertEqual(
            diff_commits[1].message,
            'New edition on side branch of the file sources for testing'
        )
        self.assertEqual(
            orig_commit.message,
            'Editing the file sources for testing #5'
        )

    def test_get_pr_info_raises(self):
        """ Test pagure.ui.fork._get_pr_info """

        gitrepo = os.path.join(self.path, 'repos', 'test.git')
        gitrepo2 = os.path.join(
            self.path, 'repos', 'forks', 'pingou', 'test.git')

        self.assertRaises(
            pagure.exceptions.BranchNotFoundException,
            pagure.lib.git.get_diff_info,
            repo_obj=PagureRepo(gitrepo2),
            orig_repo=PagureRepo(gitrepo),
            branch_from='feature',
            branch_to='master'
        )

        self.assertRaises(
            pagure.exceptions.BranchNotFoundException,
            pagure.lib.git.get_diff_info,
            repo_obj=PagureRepo(gitrepo2),
            orig_repo=PagureRepo(gitrepo),
            branch_from='feature_foo',
            branch_to='bar'
        )

    def test_diff_pull_request(self):
        """ Test pagure.lib.git.diff_pull_request """
        gitrepo = os.path.join(self.path, 'repos', 'test.git')
        gitrepo2 = os.path.join(
            self.path, 'repos', 'forks', 'pingou', 'test.git')
        request = pagure.lib.search_pull_requests(
            self.session, requestid=1, project_id=1)

        diff_commits, diff = pagure.lib.git.diff_pull_request(
            self.session,
            request=request,
            repo_obj=PagureRepo(gitrepo2),
            orig_repo=PagureRepo(gitrepo),
            requestfolder=None,
            with_diff=True
        )

        self.assertEqual(len(diff_commits), 2)
        self.assertEqual(
            diff_commits[0].message,
            'Second edit on side branch of the file sources for testing'
        )
        self.assertEqual(
            diff_commits[1].message,
            'New edition on side branch of the file sources for testing'
        )

        # Check that the PR has its PR refs
        # we don't know the task id but we'll give it 30 sec to finish
        cnt = 0
        repo = PagureRepo(gitrepo)
        while 1:
            if 'refs/pull/1/head' in list(repo.listall_references()):
                break
            cnt += 1
            if cnt == 60:
                break
            time.sleep(0.5)

        self.assertTrue(cnt < 60)

        pr_ref = repo.lookup_reference('refs/pull/1/head')
        commit = pr_ref.get_object()
        self.assertEqual(
            commit.oid.hex,
            diff_commits[0].oid.hex
        )

    def test_diff_pull_request_updated(self):
        """ Test that calling pagure.lib.git.diff_pull_request on an updated
        PR updates the PR reference
        """
        gitrepo = os.path.join(self.path, 'repos', 'test.git')
        gitrepo2 = os.path.join(
            self.path, 'repos', 'forks', 'pingou', 'test.git')
        request = pagure.lib.search_pull_requests(
            self.session, requestid=1, project_id=1)

        # Get the diff corresponding to the PR and check its ref

        diff_commits, diff = pagure.lib.git.diff_pull_request(
            self.session,
            request=request,
            repo_obj=PagureRepo(gitrepo2),
            orig_repo=PagureRepo(gitrepo),
            requestfolder=None,
            with_diff=True
        )

        self.assertEqual(len(diff_commits), 2)

        # Check that the PR has its PR refs
        # we don't know the task id but we'll give it 30 sec to finish
        cnt = 0
        repo = PagureRepo(gitrepo)
        while 1:
            if 'refs/pull/1/head' in list(repo.listall_references()):
                break
            cnt += 1
            if cnt == 60:
                break
            time.sleep(0.5)

        self.assertTrue(cnt < 60)

        pr_ref = repo.lookup_reference('refs/pull/1/head')
        commit = pr_ref.get_object()
        self.assertEqual(
            commit.oid.hex,
            diff_commits[0].oid.hex
        )

        # Add a new commit on the fork
        repopath = os.path.join(self.path, 'pingou_test2')
        clone_repo = pygit2.clone_repository(
            gitrepo2, repopath, checkout_branch='feature_foo')

        with open(os.path.join(repopath, 'sources'), 'w') as stream:
                stream.write('foo\n bar\nbaz\nhey there\n')
        clone_repo.index.add('sources')
        clone_repo.index.write()

        last_commit = clone_repo.lookup_branch('feature_foo').get_object()

        # Commits the files added
        tree = clone_repo.index.write_tree()
        author = pygit2.Signature(
            'Alice Author', 'alice@authors.tld')
        committer = pygit2.Signature(
            'Cecil Committer', 'cecil@committers.tld')
        last_commit = clone_repo.create_commit(
            'refs/heads/feature_foo',  # the name of the reference to update
            author,
            committer,
            'Third edit on side branch of the file sources for testing',
            # binary string representing the tree object ID
            tree,
            # list of binary strings representing parents of the new commit
            [last_commit.oid.hex]
        )

        # Push to the fork repo
        ori_remote = clone_repo.remotes[0]
        refname = 'refs/heads/feature_foo:refs/heads/feature_foo'
        PagureRepo.push(ori_remote, refname)

        # Get the new diff for that PR and check its new ref

        diff_commits, diff = pagure.lib.git.diff_pull_request(
            self.session,
            request=request,
            repo_obj=PagureRepo(gitrepo2),
            orig_repo=PagureRepo(gitrepo),
            requestfolder=None,
            with_diff=True
        )
        self.assertEqual(len(diff_commits), 3)

        # Check that the PR has its PR refs
        # we don't know the task id but we'll give it 30 sec to finish
        cnt = 0
        repo = PagureRepo(gitrepo)
        while 1:
            if 'refs/pull/1/head' in list(repo.listall_references()):
                break
            cnt += 1
            if cnt == 60:
                break
            time.sleep(0.5)

        self.assertTrue(cnt < 60)

        pr_ref = repo.lookup_reference('refs/pull/1/head')
        commit2 = pr_ref.get_object()
        self.assertEqual(
            commit2.oid.hex,
            diff_commits[0].oid.hex
        )
        self.assertNotEqual(
            commit.oid.hex,
            commit2.oid.hex,
        )

    def test_two_diff_pull_request_sequentially(self):
        """ Test calling pagure.lib.git.diff_pull_request twice returns
        the same data
        """
        gitrepo = os.path.join(self.path, 'repos', 'test.git')
        gitrepo2 = os.path.join(
            self.path, 'repos', 'forks', 'pingou', 'test.git')
        request = pagure.lib.search_pull_requests(
            self.session, requestid=1, project_id=1)

        # Get the diff corresponding to the PR and check its ref

        diff_commits, diff = pagure.lib.git.diff_pull_request(
            self.session,
            request=request,
            repo_obj=PagureRepo(gitrepo2),
            orig_repo=PagureRepo(gitrepo),
            requestfolder=None,
            with_diff=True
        )

        self.assertEqual(len(diff_commits), 2)

        # Check that the PR has its PR refs
        # we don't know the task id but we'll give it 30 sec to finish
        cnt = 0
        repo = PagureRepo(gitrepo)
        while 1:
            if 'refs/pull/1/head' in list(repo.listall_references()):
                break
            cnt += 1
            if cnt == 60:
                break
            time.sleep(0.5)

        self.assertTrue(cnt < 60)

        pr_ref = repo.lookup_reference('refs/pull/1/head')
        commit = pr_ref.get_object()
        self.assertEqual(
            commit.oid.hex,
            diff_commits[0].oid.hex
        )

        # Run diff_pull_request a second time

        diff_commits2, diff = pagure.lib.git.diff_pull_request(
            self.session,
            request=request,
            repo_obj=PagureRepo(gitrepo2),
            orig_repo=PagureRepo(gitrepo),
            requestfolder=None,
            with_diff=True
        )
        self.assertEqual(len(diff_commits2), 2)
        self.assertEqual(
            [d.oid.hex for d in diff_commits2],
            [d.oid.hex for d in diff_commits])

        # Check that the PR has its PR refs
        # we don't know the task id but we'll give it 30 sec to finish
        cnt = 0
        repo = PagureRepo(gitrepo)
        while 1:
            if 'refs/pull/1/head' in list(repo.listall_references()):
                break
            cnt += 1
            if cnt == 60:
                break
            time.sleep(0.5)

        self.assertTrue(cnt < 60)

        pr_ref = repo.lookup_reference('refs/pull/1/head')
        commit2 = pr_ref.get_object()
        self.assertEqual(
            commit2.oid.hex,
            diff_commits[0].oid.hex
        )

        self.assertEqual(
            commit.oid.hex,
            commit2.oid.hex
        )

if __name__ == '__main__':
    unittest.main(verbosity=2)
