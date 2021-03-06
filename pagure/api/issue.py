# -*- coding: utf-8 -*-

"""
 (c) 2015-2017 - Copyright Red Hat Inc

 Authors:
   Pierre-Yves Chibon <pingou@pingoured.fr>

"""

from __future__ import print_function

import flask
import datetime

from sqlalchemy.exc import SQLAlchemyError

import pagure
import pagure.exceptions
import pagure.lib

from pagure import (
    APP, SESSION, is_repo_committer, api_authenticated,
    urlpattern, is_repo_user
)
from pagure.api import (
    API, api_method, api_login_required, api_login_optional, APIERROR,
    get_authorized_api_project
)


def _get_repo(repo_name, username=None, namespace=None):
    """Check if repository exists and get repository name
    :param repo_name: name of repository
    :param username:
    :param namespace:
    :raises pagure.exceptions.APIError: when repository doesn't exist or
        is disabled
    :return: repository name
    """
    repo = get_authorized_api_project(
        SESSION, repo_name, user=username, namespace=namespace)

    if repo is None:
        raise pagure.exceptions.APIError(
            404, error_code=APIERROR.ENOPROJECT)

    return repo


def _check_issue_tracker(repo):
    """Check if issue tracker is enabled for repository
    :param repo: repository
    :raises pagure.exceptions.APIError: when issue tracker is disabled
    """
    if not repo.settings.get('issue_tracker', True):
        raise pagure.exceptions.APIError(
            404, error_code=APIERROR.ETRACKERDISABLED)


def _check_token(repo, project_token=True):
    """Check if token is valid for the repo
    :param repo: repository name
    :param project_token: set True when project token is required,
        otherwise any token can be used
    :raises pagure.exceptions.APIError: when token is not valid for repo
    """
    if api_authenticated():
        # if there is a project associated with the token, check it
        # if there is no project associated, check if it is required
        if (flask.g.token.project is not None
                and repo != flask.g.token.project) \
                or (flask.g.token.project is None and project_token):
            raise pagure.exceptions.APIError(
                401, error_code=APIERROR.EINVALIDTOK)


def _get_issue(repo, issueid, issueuid=None):
    """Get issue and check permissions
    :param repo: repository name
    :param issueid: issue ID
    :param issueuid: issue Unique ID
    :raises pagure.exceptions.APIError: when issues doesn't exists
    :return: issue
    """
    issue = pagure.lib.search_issues(
        SESSION, repo, issueid=issueid, issueuid=issueuid)

    if issue is None or issue.project != repo:
        raise pagure.exceptions.APIError(404, error_code=APIERROR.ENOISSUE)

    return issue


def _check_private_issue_access(issue):
    """Check if user can access issue. Must be repo commiter
    or author to see private issues.
    :param issue: issue object
    :raises pagure.exceptions.APIError: when access denied
    """
    if (
        issue.private
        and not is_repo_committer(issue.project)
        and (
            not api_authenticated()
            or not issue.user.user == flask.g.fas_user.username
        )
    ):
        raise pagure.exceptions.APIError(
            403, error_code=APIERROR.EISSUENOTALLOWED)


def _check_ticket_access(issue, assignee=False):
    """Check if user can access issue. Must be repo commiter
    or author to see private issues.
    :param issue: issue object
    :param assignee: a boolean specifying whether to allow the assignee or not
        defaults to False
    :raises pagure.exceptions.APIError: when access denied
    """
    # Private tickets require commit access
    _check_private_issue_access(issue)
    # Public tickets require ticket access
    error = not is_repo_user(issue.project)

    if assignee:
        if issue.assignee is not None \
                and issue.assignee.user == flask.g.fas_user.username:
            error = False

    if error:
        raise pagure.exceptions.APIError(
            403, error_code=APIERROR.EISSUENOTALLOWED)


def _check_link_custom_field(field, links):
    """Check if the value provided in the link custom field
    is a link.
    :param field : The issue custom field key object.
    :param links : Value of the custom field.
    :raises pagure.exceptions.APIERROR when invalid.
    """
    if field.key_type == 'link':
        links = links.split(',')
        for link in links:
            link = link.replace(' ', '')
            if not urlpattern.match(link):
                raise pagure.exceptions.APIError(
                    400, error_code=APIERROR.EINVALIDISSUEFIELD_LINK)


@API.route('/<repo>/new_issue', methods=['POST'])
@API.route('/<namespace>/<repo>/new_issue', methods=['POST'])
@API.route('/fork/<username>/<repo>/new_issue', methods=['POST'])
@API.route('/fork/<username>/<namespace>/<repo>/new_issue', methods=['POST'])
@api_login_required(acls=['issue_create'])
@api_method
def api_new_issue(repo, username=None, namespace=None):
    """
    Create a new issue
    ------------------
    Open a new issue on a project.

    ::

        POST /api/0/<repo>/new_issue
        POST /api/0/<namespace>/<repo>/new_issue

    ::

        POST /api/0/fork/<username>/<repo>/new_issue
        POST /api/0/fork/<username>/<namespace>/<repo>/new_issue

    Input
    ^^^^^

    +-------------------+--------+-------------+---------------------------+
    | Key               | Type   | Optionality | Description               |
    +===================+========+=============+===========================+
    | ``title``         | string | Mandatory   | The title of the issue    |
    +-------------------+--------+-------------+---------------------------+
    | ``issue_content`` | string | Mandatory   | | The description of the  |
    |                   |        |             |   issue                   |
    +-------------------+--------+-------------+---------------------------+
    | ``private``       | boolean| Optional    | | Include this key if     |
    |                   |        |             |   you want a private issue|
    |                   |        |             |   to be created           |
    +-------------------+--------+-------------+---------------------------+
    | ``priority``      | string | Optional    | | The priority to set to  |
    |                   |        |             |   this ticket from the    |
    |                   |        |             |   list of priorities set  |
    |                   |        |             |   in the project          |
    +-------------------+--------+-------------+---------------------------+
    | ``milestone``     | string | Optional    | | The milestone to assign |
    |                   |        |             |   to this ticket from the |
    |                   |        |             |   list of milestones set  |
    |                   |        |             |   in the project          |
    +-------------------+--------+-------------+---------------------------+
    | ``tag``           | string | Optional    | | Comma separated list of |
    |                   |        |             |   tags to link to this    |
    |                   |        |             |   ticket from the list of |
    |                   |        |             |   tags in the project     |
    +-------------------+--------+-------------+---------------------------+
    | ``assignee``      | string | Optional    | | The username of the user|
    |                   |        |             |   to assign this ticket to|
    +-------------------+--------+-------------+---------------------------+

    Sample response
    ^^^^^^^^^^^^^^^

    ::

        {
          "issue": {
            "assignee": null,
            "blocks": [],
            "close_status": null,
            "closed_at": null,
            "comments": [],
            "content": "This issue needs attention",
            "custom_fields": [],
            "date_created": "1479458613",
            "depends": [],
            "id": 1,
            "milestone": null,
            "priority": null,
            "private": false,
            "status": "Open",
            "tags": [],
            "title": "test issue",
            "user": {
              "fullname": "PY C",
              "name": "pingou"
            }
          },
          "message": "Issue created"
        }

    """
    output = {}
    repo = _get_repo(repo, username, namespace)
    _check_issue_tracker(repo)
    _check_token(repo, project_token=False)

    user_obj = pagure.lib.get_user(
        SESSION, flask.g.fas_user.username)
    if not user_obj:
        raise pagure.exceptions.APIError(404, error_code=APIERROR.ENOUSER)

    form = pagure.forms.IssueFormSimplied(
        priorities=repo.priorities,
        milestones=repo.milestones,
        csrf_enabled=False)
    if form.validate_on_submit():
        title = form.title.data
        content = form.issue_content.data
        milestone = form.milestone.data or None
        private = str(form.private.data).lower() in ['true', '1']
        priority = form.priority.data or None
        assignee = flask.request.form.get(
            'assignee', '').strip() or None
        tags = [
            tag.strip()
            for tag in flask.request.form.get(
                'tag', '').split(',')
            if tag.strip()]

        try:
            issue = pagure.lib.new_issue(
                SESSION,
                repo=repo,
                title=title,
                content=content,
                private=private,
                assignee=assignee,
                milestone=milestone,
                priority=priority,
                tags=tags,
                user=flask.g.fas_user.username,
                ticketfolder=APP.config['TICKETS_FOLDER'],
            )
            SESSION.flush()
            # If there is a file attached, attach it.
            filestream = flask.request.files.get('filestream')
            if filestream and '<!!image>' in issue.content:
                new_filename = pagure.lib.add_attachment(
                    repo=repo,
                    issue=issue,
                    attachmentfolder=APP.config['ATTACHMENTS_FOLDER'],
                    user=user_obj,
                    filename=filestream.filename,
                    filestream=filestream.stream,
                )
                # Replace the <!!image> tag in the comment with the link
                # to the actual image
                filelocation = flask.url_for(
                    'view_issue_raw_file',
                    repo=repo.name,
                    username=username,
                    filename=new_filename,
                )
                new_filename = new_filename.split('-', 1)[1]
                url = '[![%s](%s)](%s)' % (
                    new_filename, filelocation, filelocation)
                issue.content = issue.content.replace('<!!image>', url)
                SESSION.add(issue)
                SESSION.flush()

            SESSION.commit()
            output['message'] = 'Issue created'
            output['issue'] = issue.to_json(public=True)
        except SQLAlchemyError as err:  # pragma: no cover
            SESSION.rollback()
            APP.logger.exception(err)
            raise pagure.exceptions.APIError(400, error_code=APIERROR.EDBERROR)

    else:
        raise pagure.exceptions.APIError(
            400, error_code=APIERROR.EINVALIDREQ, errors=form.errors)

    jsonout = flask.jsonify(output)
    return jsonout


@API.route('/<namespace>/<repo>/issues')
@API.route('/fork/<username>/<repo>/issues')
@API.route('/<repo>/issues')
@API.route('/fork/<username>/<namespace>/<repo>/issues')
@api_login_optional()
@api_method
def api_view_issues(repo, username=None, namespace=None):
    """
    List project's issues
    ---------------------
    List issues of a project.

    ::

        GET /api/0/<repo>/issues
        GET /api/0/<namespace>/<repo>/issues

    ::

        GET /api/0/fork/<username>/<repo>/issues
        GET /api/0/fork/<username>/<namespace>/<repo>/issues

    Parameters
    ^^^^^^^^^^

    +---------------+---------+--------------+---------------------------+
    | Key           | Type    | Optionality  | Description               |
    +===============+=========+==============+===========================+
    | ``status``    | string  | Optional     | | Filters the status of   |
    |               |         |              |   issues. Fetches all the |
    |               |         |              |   issues if status is     |
    |               |         |              |   ``all``. Default:       |
    |               |         |              |   ``Open``                |
    +---------------+---------+--------------+---------------------------+
    | ``tags``      | string  | Optional     | | A list of tags you      |
    |               |         |              |   wish to filter. If      |
    |               |         |              |   you want to filter      |
    |               |         |              |   for issues not having   |
    |               |         |              |   a tag, add an           |
    |               |         |              |   exclamation mark in     |
    |               |         |              |   front of it             |
    +---------------+---------+--------------+---------------------------+
    | ``assignee``  | string  | Optional     | | Filter the issues       |
    |               |         |              |   by assignee             |
    +---------------+---------+--------------+---------------------------+
    | ``author``    | string  | Optional     | | Filter the issues       |
    |               |         |              |   by creator              |
    +---------------+---------+--------------+---------------------------+
    | ``milestones``| list of | Optional     | | Filter the issues       |
    |               | strings |              |   by milestone            |
    +---------------+---------+--------------+---------------------------+
    | ``priority``  | string  | Optional     | | Filter the issues       |
    |               |         |              |   by priority             |
    +---------------+---------+--------------+---------------------------+
    | ``no_stones`` | boolean | Optional     | | If true returns only the|
    |               |         |              |   issues having no        |
    |               |         |              |   milestone, if false     |
    |               |         |              |   returns only the issues |
    |               |         |              |   having a milestone      |
    +---------------+---------+--------------+---------------------------+
    | ``since``     | string  | Optional     | | Filter the issues       |
    |               |         |              |   updated after this date.|
    |               |         |              |   The date can either be  |
    |               |         |              |   provided as an unix date|
    |               |         |              |   or in the format Y-M-D  |
    +---------------+---------+--------------+---------------------------+
    | ``order``     | string  | Optional     | | Set the ordering of the |
    |               |         |              |   issues. This can be     |
    |               |         |              |   ``asc`` or ``desc``.    |
    |               |         |              |   Default: ``desc``       |
    +---------------+---------+--------------+---------------------------+

    Sample response
    ^^^^^^^^^^^^^^^

    ::

        {
          "args": {
            "assignee": null,
            "author": null,
            'milestones': [],
            'no_stones': null,
            'order': null,
            'priority': null,
            "since": null,
            "status": "Closed",
            "tags": [
              "0.1"
            ]
          },
          "total_issues": 1,
          "issues": [
            {
              "assignee": null,
              "blocks": ["1"],
              "comments": [],
              "content": "asd",
              "date_created": "1427442217",
              "depends": [],
              "id": 4,
              "private": false,
              "status": "Fixed",
              "tags": [
                "0.1"
              ],
              "title": "bug",
              "user": {
                "fullname": "PY.C",
                "name": "pingou"
              }
            }
          ]
        }

    """
    repo = _get_repo(repo, username, namespace)
    _check_issue_tracker(repo)
    _check_token(repo)

    assignee = flask.request.args.get('assignee', None)
    author = flask.request.args.get('author', None)
    milestone = flask.request.args.getlist('milestones', None)
    no_stones = flask.request.args.get('no_stones', None)
    if no_stones is not None:
        if str(no_stones).lower() in ['1', 'true', 't']:
            no_stones = True
        else:
            no_stones = False
    priority = flask.request.args.get('priority', None)
    since = flask.request.args.get('since', None)
    order = flask.request.args.get('order', None)
    status = flask.request.args.get('status', None)
    tags = flask.request.args.getlist('tags')
    tags = [tag.strip() for tag in tags if tag.strip()]

    priority_key = None
    if priority:
        found = False
        if priority in repo.priorities:
            found = True
            priority_key = int(priority)
        else:
            for key, val in repo.priorities.items():
                if val.lower() == priority.lower():
                    priority_key = key
                    found = True
                    break

        if not found:
            raise pagure.exceptions.APIError(
                400, error_code=APIERROR.EINVALIDPRIORITY)

    # Hide private tickets
    private = False
    # If user is authenticated, show him/her his/her private tickets
    if api_authenticated():
        private = flask.g.fas_user.username
    # If user is repo committer, show all tickets included the private ones
    if is_repo_committer(repo):
        private = None

    params = {
        'session': SESSION,
        'repo': repo,
        'tags': tags,
        'assignee': assignee,
        'author': author,
        'private': private,
        'milestones': milestone,
        'priority': priority_key,
        'order': order,
        'no_milestones': no_stones,
    }

    if status is not None:
        if status.lower() == 'all':
            params.update({'status': None})
        elif status.lower() == 'closed':
            params.update({'closed': True})
        else:
            params.update({'status': status})
    else:
        params.update({'status': 'Open'})

    updated_after = None
    if since:
        # Validate and convert the time
        if since.isdigit():
            # We assume its a timestamp, so convert it to datetime
            try:
                updated_after = datetime.datetime.fromtimestamp(int(since))
            except ValueError:
                raise pagure.exceptions.APIError(
                    400, error_code=APIERROR.ETIMESTAMP)
        else:
            # We assume datetime format, so validate it
            try:
                updated_after = datetime.datetime.strptime(since, '%Y-%m-%d')
            except ValueError:
                raise pagure.exceptions.APIError(
                    400, error_code=APIERROR.EDATETIME)

    params.update({'updated_after': updated_after})
    issues = pagure.lib.search_issues(**params)
    jsonout = flask.jsonify({
        'total_issues': len(issues),
        'issues': [issue.to_json(public=True) for issue in issues],
        'args': {
            'assignee': assignee,
            'author': author,
            'milestones': milestone,
            'no_stones': no_stones,
            'order': order,
            'priority': priority,
            'since': since,
            'status': status,
            'tags': tags,
        }
    })
    return jsonout


@API.route('/<repo>/issue/<issueid>')
@API.route('/<namespace>/<repo>/issue/<issueid>')
@API.route('/fork/<username>/<repo>/issue/<issueid>')
@API.route('/fork/<username>/<namespace>/<repo>/issue/<issueid>')
@api_login_optional()
@api_method
def api_view_issue(repo, issueid, username=None, namespace=None):
    """
    Issue information
    -----------------
    Retrieve information of a specific issue.

    ::

        GET /api/0/<repo>/issue/<issue id>
        GET /api/0/<namespace>/<repo>/issue/<issue id>

    ::

        GET /api/0/fork/<username>/<repo>/issue/<issue id>
        GET /api/0/fork/<username>/<namespace>/<repo>/issue/<issue id>

    The identifier provided can be either the unique identifier or the
    regular identifier used in the UI (for example ``24`` in
    ``/forks/user/test/issue/24``)

    Sample response
    ^^^^^^^^^^^^^^^

    ::

        {
          "assignee": null,
          "blocks": [],
          "comments": [],
          "content": "This issue needs attention",
          "date_created": "1431414800",
          "depends": ["4"],
          "id": 1,
          "private": false,
          "status": "Open",
          "tags": [],
          "title": "test issue",
          "user": {
            "fullname": "PY C",
            "name": "pingou"
          }
        }

    """
    comments = flask.request.args.get('comments', True)
    if str(comments).lower() in ['0', 'False']:
        comments = False

    repo = _get_repo(repo, username, namespace)
    _check_issue_tracker(repo)
    _check_token(repo)

    issue_id = issue_uid = None
    try:
        issue_id = int(issueid)
    except (ValueError, TypeError):
        issue_uid = issueid

    issue = _get_issue(repo, issue_id, issueuid=issue_uid)
    _check_private_issue_access(issue)

    jsonout = flask.jsonify(
        issue.to_json(public=True, with_comments=comments))
    return jsonout


@API.route('/<repo>/issue/<issueid>/comment/<int:commentid>')
@API.route('/<namespace>/<repo>/issue/<issueid>/comment/<int:commentid>')
@API.route('/fork/<username>/<repo>/issue/<issueid>/comment/<int:commentid>')
@API.route(
    '/fork/<username>/<namespace>/<repo>/issue/<issueid>/'
    'comment/<int:commentid>')
@api_login_optional()
@api_method
def api_view_issue_comment(
        repo, issueid, commentid, username=None, namespace=None):
    """
    Comment of an issue
    --------------------
    Retrieve a specific comment of an issue.

    ::

        GET /api/0/<repo>/issue/<issue id>/comment/<comment id>
        GET /api/0/<namespace>/<repo>/issue/<issue id>/comment/<comment id>

    ::

        GET /api/0/fork/<username>/<repo>/issue/<issue id>/comment/<comment id>
        GET /api/0/fork/<username>/<namespace>/<repo>/issue/<issue id>/comment/<comment id>

    The identifier provided can be either the unique identifier or the
    regular identifier used in the UI (for example ``24`` in
    ``/forks/user/test/issue/24``)

    Sample response
    ^^^^^^^^^^^^^^^

    ::

        {
          "avatar_url": "https://seccdn.libravatar.org/avatar/...",
          "comment": "9",
          "comment_date": "2015-07-01 15:08",
          "date_created": "1435756127",
          "id": 464,
          "parent": null,
          "user": {
            "fullname": "P.-Y.C.",
            "name": "pingou"
          }
        }

    """  # noqa: E501

    repo = _get_repo(repo, username, namespace)
    _check_issue_tracker(repo)
    _check_token(repo)

    issue_id = issue_uid = None
    try:
        issue_id = int(issueid)
    except (ValueError, TypeError):
        issue_uid = issueid

    issue = _get_issue(repo, issue_id, issueuid=issue_uid)
    _check_private_issue_access(issue)

    comment = pagure.lib.get_issue_comment(SESSION, issue.uid, commentid)
    if not comment:
        raise pagure.exceptions.APIError(
            404, error_code=APIERROR.ENOCOMMENT)

    output = comment.to_json(public=True)
    output['avatar_url'] = pagure.lib.avatar_url_from_email(
        comment.user.default_email, size=16)
    output['comment_date'] = comment.date_created.strftime(
        '%Y-%m-%d %H:%M:%S')
    jsonout = flask.jsonify(output)
    return jsonout


@API.route('/<repo>/issue/<int:issueid>/status', methods=['POST'])
@API.route('/<namespace>/<repo>/issue/<int:issueid>/status', methods=['POST'])
@API.route(
    '/fork/<username>/<repo>/issue/<int:issueid>/status', methods=['POST'])
@API.route(
    '/fork/<username>/<namespace>/<repo>/issue/<int:issueid>/status',
    methods=['POST'])
@api_login_required(acls=['issue_change_status', 'issue_update'])
@api_method
def api_change_status_issue(repo, issueid, username=None, namespace=None):
    """
    Change issue status
    -------------------
    Change the status of an issue.

    ::

        POST /api/0/<repo>/issue/<issue id>/status
        POST /api/0/<namespace>/<repo>/issue/<issue id>/status

    ::

        POST /api/0/fork/<username>/<repo>/issue/<issue id>/status
        POST /api/0/fork/<username>/<namespace>/<repo>/issue/<issue id>/status

    Input
    ^^^^^

    +------------------+---------+--------------+------------------------+
    | Key              | Type    | Optionality  | Description            |
    +==================+=========+==============+========================+
    | ``close_status`` | string  | Optional     | The close status of    |
    |                  |         |              | the issue              |
    +------------------+---------+--------------+------------------------+
    | ``status``       | string  | Mandatory    | The new status of the  |
    |                  |         |              | issue, can be 'Open' or|
    |                  |         |              | 'Closed'               |
    +------------------+---------+--------------+------------------------+

    Sample response
    ^^^^^^^^^^^^^^^

    ::

        {
          "message": "Successfully edited issue #1"
        }

    """
    output = {}

    repo = _get_repo(repo, username, namespace)
    _check_issue_tracker(repo)
    _check_token(repo, project_token=False)

    issue = _get_issue(repo, issueid)
    _check_ticket_access(issue)

    status = pagure.lib.get_issue_statuses(SESSION)
    form = pagure.forms.StatusForm(
        status=status,
        close_status=repo.close_status,
        csrf_enabled=False)

    if not pagure.is_repo_user(repo) \
            and flask.g.fas_user.username != issue.user.user:
        raise pagure.exceptions.APIError(
            403, error_code=APIERROR.EISSUENOTALLOWED)

    close_status = None
    if form.close_status.raw_data:
        close_status = form.close_status.data
    new_status = form.status.data.strip()
    if new_status in repo.close_status and not close_status:
        close_status = new_status
        new_status = 'Closed'
        form.status.data = new_status

    if form.validate_on_submit():
        try:
            # Update status
            message = pagure.lib.edit_issue(
                SESSION,
                issue=issue,
                status=new_status,
                close_status=close_status,
                user=flask.g.fas_user.username,
                ticketfolder=APP.config['TICKETS_FOLDER'],
            )
            SESSION.commit()
            if message:
                output['message'] = message
            else:
                output['message'] = 'No changes'

            if message:
                pagure.lib.add_metadata_update_notif(
                    session=SESSION,
                    obj=issue,
                    messages=message,
                    user=flask.g.fas_user.username,
                    gitfolder=APP.config['TICKETS_FOLDER']
                )
        except pagure.exceptions.PagureException as err:
            raise pagure.exceptions.APIError(
                400, error_code=APIERROR.ENOCODE, error=str(err))
        except SQLAlchemyError as err:  # pragma: no cover
            SESSION.rollback()
            raise pagure.exceptions.APIError(400, error_code=APIERROR.EDBERROR)

    else:
        raise pagure.exceptions.APIError(
            400, error_code=APIERROR.EINVALIDREQ, errors=form.errors)

    jsonout = flask.jsonify(output)
    return jsonout


@API.route('/<repo>/issue/<int:issueid>/milestone', methods=['POST'])
@API.route(
    '/<namespace>/<repo>/issue/<int:issueid>/milestone', methods=['POST'])
@API.route(
    '/fork/<username>/<repo>/issue/<int:issueid>/milestone',
    methods=['POST'])
@API.route(
    '/fork/<username>/<namespace>/<repo>/issue/<int:issueid>/milestone',
    methods=['POST'])
@api_login_required(acls=['issue_update_milestone', 'issue_update'])
@api_method
def api_change_milestone_issue(repo, issueid, username=None, namespace=None):
    """
    Change issue milestone
    ----------------------
    Change the milestone of an issue.

    ::

        POST /api/0/<repo>/issue/<issue id>/milestone
        POST /api/0/<namespace>/<repo>/issue/<issue id>/milestone

    ::

        POST /api/0/fork/<username>/<repo>/issue/<issue id>/milestone
        POST /api/0/fork/<username>/<namespace>/<repo>/issue/<issue id>/milestone

    Input
    ^^^^^

    +------------------+---------+--------------+------------------------+
    | Key              | Type    | Optionality  | Description            |
    +==================+=========+==============+========================+
    | ``milestone``    | string  | Optional     | The new milestone of   |
    |                  |         |              | the issue, can be any  |
    |                  |         |              | of defined milestones  |
    |                  |         |              | or empty to unset the  |
    |                  |         |              | milestone              |
    +------------------+---------+--------------+------------------------+

    Sample response
    ^^^^^^^^^^^^^^^

    ::

        {
          "message": "Successfully edited issue #1"
        }

    """  # noqa
    output = {}
    repo = _get_repo(repo, username, namespace)
    _check_issue_tracker(repo)
    _check_token(repo)

    issue = _get_issue(repo, issueid)
    _check_ticket_access(issue)

    form = pagure.forms.MilestoneForm(
        milestones=repo.milestones.keys(),
        csrf_enabled=False)

    if form.validate_on_submit():
        new_milestone = form.milestone.data
        if new_milestone == '':
            new_milestone = None  # unset milestone
        try:
            # Update status
            message = pagure.lib.edit_issue(
                SESSION,
                issue=issue,
                milestone=new_milestone,
                user=flask.g.fas_user.username,
                ticketfolder=APP.config['TICKETS_FOLDER'],
            )
            SESSION.commit()
            if message:
                output['message'] = message
            else:
                output['message'] = 'No changes'

            if message:
                pagure.lib.add_metadata_update_notif(
                    session=SESSION,
                    obj=issue,
                    messages=message,
                    user=flask.g.fas_user.username,
                    gitfolder=APP.config['TICKETS_FOLDER']
                )
        except pagure.exceptions.PagureException as err:
            raise pagure.exceptions.APIError(
                400, error_code=APIERROR.ENOCODE, error=str(err))
        except SQLAlchemyError as err:  # pragma: no cover
            SESSION.rollback()
            raise pagure.exceptions.APIError(400, error_code=APIERROR.EDBERROR)

    else:
        raise pagure.exceptions.APIError(
            400, error_code=APIERROR.EINVALIDREQ, errors=form.errors)

    jsonout = flask.jsonify(output)
    return jsonout


@API.route('/<repo>/issue/<int:issueid>/comment', methods=['POST'])
@API.route('/<namespace>/<repo>/issue/<int:issueid>/comment', methods=['POST'])
@API.route(
    '/fork/<username>/<repo>/issue/<int:issueid>/comment', methods=['POST'])
@API.route(
    '/fork/<username>/<namespace>/<repo>/issue/<int:issueid>/comment',
    methods=['POST'])
@api_login_required(acls=['issue_comment', 'issue_update'])
@api_method
def api_comment_issue(repo, issueid, username=None, namespace=None):
    """
    Comment to an issue
    -------------------
    Add a comment to an issue.

    ::

        POST /api/0/<repo>/issue/<issue id>/comment
        POST /api/0/<namespace>/<repo>/issue/<issue id>/comment

    ::

        POST /api/0/fork/<username>/<repo>/issue/<issue id>/comment
        POST /api/0/fork/<username>/<namespace>/<repo>/issue/<issue id>/comment

    Input
    ^^^^^

    +--------------+----------+---------------+---------------------------+
    | Key          | Type     | Optionality   | Description               |
    +==============+==========+===============+===========================+
    | ``comment``  | string   | Mandatory     | | The comment to add to   |
    |              |          |               |   the issue               |
    +--------------+----------+---------------+---------------------------+

    Sample response
    ^^^^^^^^^^^^^^^

    ::

        {
          "message": "Comment added"
        }

    """
    output = {}
    repo = _get_repo(repo, username, namespace)
    _check_issue_tracker(repo)
    _check_token(repo, project_token=False)

    issue = _get_issue(repo, issueid)
    _check_private_issue_access(issue)

    form = pagure.forms.CommentForm(csrf_enabled=False)
    if form.validate_on_submit():
        comment = form.comment.data
        try:
            # New comment
            message = pagure.lib.add_issue_comment(
                SESSION,
                issue=issue,
                comment=comment,
                user=flask.g.fas_user.username,
                ticketfolder=APP.config['TICKETS_FOLDER'],
            )
            SESSION.commit()
            output['message'] = message
        except SQLAlchemyError as err:  # pragma: no cover
            SESSION.rollback()
            APP.logger.exception(err)
            raise pagure.exceptions.APIError(400, error_code=APIERROR.EDBERROR)

    else:
        raise pagure.exceptions.APIError(
            400, error_code=APIERROR.EINVALIDREQ, errors=form.errors)

    jsonout = flask.jsonify(output)
    return jsonout


@API.route('/<repo>/issue/<int:issueid>/assign', methods=['POST'])
@API.route('/<namespace>/<repo>/issue/<int:issueid>/assign', methods=['POST'])
@API.route(
    '/fork/<username>/<repo>/issue/<int:issueid>/assign', methods=['POST'])
@API.route(
    '/fork/<username>/<namespace>/<repo>/issue/<int:issueid>/assign',
    methods=['POST'])
@api_login_required(acls=['issue_assign', 'issue_update'])
@api_method
def api_assign_issue(repo, issueid, username=None, namespace=None):
    """
    Assign an issue
    ---------------
    Assign an issue to someone.

    ::

        POST /api/0/<repo>/issue/<issue id>/assign
        POST /api/0/<namespace>/<repo>/issue/<issue id>/assign

    ::

        POST /api/0/fork/<username>/<repo>/issue/<issue id>/assign
        POST /api/0/fork/<username>/<namespace>/<repo>/issue/<issue id>/assign

    Input
    ^^^^^

    +--------------+----------+---------------+---------------------------+
    | Key          | Type     | Optionality   | Description               |
    +==============+==========+===============+===========================+
    | ``assignee`` | string   | Mandatory     | | The username of the user|
    |              |          |               |   to assign the issue to. |
    +--------------+----------+---------------+---------------------------+

    Sample response
    ^^^^^^^^^^^^^^^

    ::

        {
          "message": "Issue assigned"
        }

    """
    output = {}
    repo = _get_repo(repo, username, namespace)
    _check_issue_tracker(repo)
    _check_token(repo)

    issue = _get_issue(repo, issueid)
    _check_ticket_access(issue, assignee=True)

    form = pagure.forms.AssignIssueForm(csrf_enabled=False)
    if form.validate_on_submit():
        assignee = form.assignee.data or None
        # Create our metadata comment object
        try:
            # New comment
            message = pagure.lib.add_issue_assignee(
                SESSION,
                issue=issue,
                assignee=assignee,
                user=flask.g.fas_user.username,
                ticketfolder=APP.config['TICKETS_FOLDER'],
            )
            SESSION.commit()
            if message:
                pagure.lib.add_metadata_update_notif(
                    session=SESSION,
                    obj=issue,
                    messages=message,
                    user=flask.g.fas_user.username,
                    gitfolder=APP.config['TICKETS_FOLDER']
                )
                output['message'] = message
            else:
                output['message'] = 'Nothing to change'
        except pagure.exceptions.PagureException as err:  # pragma: no cover
            raise pagure.exceptions.APIError(
                400, error_code=APIERROR.ENOCODE, error=str(err))
        except SQLAlchemyError as err:  # pragma: no cover
            SESSION.rollback()
            APP.logger.exception(err)
            raise pagure.exceptions.APIError(400, error_code=APIERROR.EDBERROR)

    else:
        raise pagure.exceptions.APIError(
            400, error_code=APIERROR.EINVALIDREQ, errors=form.errors)

    jsonout = flask.jsonify(output)
    return jsonout


@API.route('/<repo>/issue/<int:issueid>/subscribe', methods=['POST'])
@API.route(
    '/<namespace>/<repo>/issue/<int:issueid>/subscribe', methods=['POST'])
@API.route(
    '/fork/<username>/<repo>/issue/<int:issueid>/subscribe', methods=['POST'])
@API.route(
    '/fork/<username>/<namespace>/<repo>/issue/<int:issueid>/subscribe',
    methods=['POST'])
@api_login_required(acls=['issue_subscribe'])
@api_method
def api_subscribe_issue(repo, issueid, username=None, namespace=None):
    """
    Subscribe to an issue
    ---------------------
    Allows someone to subscribe to or unsubscribe from the notifications
    related to an issue.

    ::

        POST /api/0/<repo>/issue/<issue id>/subscribe
        POST /api/0/<namespace>/<repo>/issue/<issue id>/subscribe

    ::

        POST /api/0/fork/<username>/<repo>/issue/<issue id>/subscribe
        POST /api/0/fork/<username>/<namespace>/<repo>/issue/<issue id>/subscribe

    Input
    ^^^^^

    +--------------+----------+---------------+---------------------------+
    | Key          | Type     | Optionality   | Description               |
    +==============+==========+===============+===========================+
    | ``status``   | boolean  | Mandatory     | The intended subscription |
    |              |          |               | status. ``true`` for      |
    |              |          |               | subscribing, ``false``    |
    |              |          |               | for unsubscribing.        |
    +--------------+----------+---------------+---------------------------+

    Sample response
    ^^^^^^^^^^^^^^^

    ::

        {
          "message": "User subscribed"
        }

    """  # noqa
    output = {}
    repo = _get_repo(repo, username, namespace)
    _check_issue_tracker(repo)
    _check_token(repo)

    issue = _get_issue(repo, issueid)
    _check_private_issue_access(issue)

    form = pagure.forms.SubscribtionForm(csrf_enabled=False)
    if form.validate_on_submit():
        status = str(form.status.data).strip().lower() in ['1', 'true']
        try:
            # Toggle subscribtion
            message = pagure.lib.set_watch_obj(
                SESSION,
                user=flask.g.fas_user.username,
                obj=issue,
                watch_status=status
            )
            SESSION.commit()
            output['message'] = message
        except SQLAlchemyError as err:  # pragma: no cover
            SESSION.rollback()
            APP.logger.exception(err)
            raise pagure.exceptions.APIError(400, error_code=APIERROR.EDBERROR)

    else:
        raise pagure.exceptions.APIError(
            400, error_code=APIERROR.EINVALIDREQ, errors=form.errors)

    jsonout = flask.jsonify(output)
    return jsonout


@API.route('/<repo>/issue/<int:issueid>/custom/<field>', methods=['POST'])
@API.route(
    '/<namespace>/<repo>/issue/<int:issueid>/custom/<field>',
    methods=['POST'])
@API.route(
    '/fork/<username>/<repo>/issue/<int:issueid>/custom/<field>',
    methods=['POST'])
@API.route(
    '/fork/<username>/<namespace>/<repo>/issue/<int:issueid>/custom/<field>',
    methods=['POST'])
@api_login_required(acls=['issue_update_custom_fields', 'issue_update'])
@api_method
def api_update_custom_field(
        repo, issueid, field, username=None, namespace=None):
    """
    Update custom field
    -------------------
    Update or reset the content of a custom field associated to an issue.

    ::

        POST /api/0/<repo>/issue/<issue id>/custom/<field>
        POST /api/0/<namespace>/<repo>/issue/<issue id>/custom/<field>

    ::

        POST /api/0/fork/<username>/<repo>/issue/<issue id>/custom/<field>
        POST /api/0/fork/<username>/<namespace>/<repo>/issue/<issue id>/custom/<field>

    Input
    ^^^^^

    +------------------+---------+--------------+-------------------------+
    | Key              | Type    | Optionality  | Description             |
    +==================+=========+==============+=========================+
    | ``value``        | string  | Optional     | The new value of the    |
    |                  |         |              | custom field of interest|
    +------------------+---------+--------------+-------------------------+

    Sample response
    ^^^^^^^^^^^^^^^

    ::

        {
          "message": "Custom field adjusted"
        }

    """  # noqa
    output = {}
    repo = _get_repo(repo, username, namespace)
    _check_issue_tracker(repo)
    _check_token(repo)

    issue = _get_issue(repo, issueid)
    _check_ticket_access(issue)

    fields = {k.name: k for k in repo.issue_keys}
    if field not in fields:
        raise pagure.exceptions.APIError(
            400, error_code=APIERROR.EINVALIDISSUEFIELD)

    key = fields[field]
    value = flask.request.form.get('value')
    if value:
        _check_link_custom_field(key, value)
    try:
        message = pagure.lib.set_custom_key_value(
            SESSION, issue, key, value)

        SESSION.commit()
        if message:
            output['message'] = message
            pagure.lib.add_metadata_update_notif(
                session=SESSION,
                obj=issue,
                messages=message,
                user=flask.g.fas_user.username,
                gitfolder=APP.config['TICKETS_FOLDER']
            )
        else:
            output['message'] = 'No changes'
    except pagure.exceptions.PagureException as err:
        raise pagure.exceptions.APIError(
            400, error_code=APIERROR.ENOCODE, error=str(err))
    except SQLAlchemyError as err:  # pragma: no cover
        print(err)
        SESSION.rollback()
        raise pagure.exceptions.APIError(400, error_code=APIERROR.EDBERROR)

    jsonout = flask.jsonify(output)
    return jsonout


@API.route('/<repo>/issue/<int:issueid>/custom', methods=['POST'])
@API.route(
    '/<namespace>/<repo>/issue/<int:issueid>/custom',
    methods=['POST'])
@API.route(
    '/fork/<username>/<repo>/issue/<int:issueid>/custom',
    methods=['POST'])
@API.route(
    '/fork/<username>/<namespace>/<repo>/issue/<int:issueid>/custom',
    methods=['POST'])
@api_login_required(acls=['issue_update_custom_fields', 'issue_update'])
@api_method
def api_update_custom_fields(
        repo, issueid, username=None, namespace=None):
    """
    Update custom fields
    --------------------
    Update or reset the content of a collection of custom fields
    associated to an issue.

    ::

        POST /api/0/<repo>/issue/<issue id>/custom
        POST /api/0/<namespace>/<repo>/issue/<issue id>/custom

    ::

        POST /api/0/fork/<username>/<repo>/issue/<issue id>/custom
        POST /api/0/fork/<username>/<namespace>/<repo>/issue/<issue id>/custom

    Input
    ^^^^^

    +------------------+---------+--------------+-----------------------------+
    | Key              | Type    | Optionality  | Description                 |
    +==================+=========+==============+=============================+
    | ``myfields``     | dict    | Mandatory    | A dictionary with the fields|
    |                  |         |              | name as key and the value   |
    +------------------+---------+--------------+-----------------------------+

    Sample payload
    ^^^^^^^^^^^^^^

    ::

      {
         "myField": "to do",
         "myField_1": "test",
         "myField_2": "done",
      }

    Sample response
    ^^^^^^^^^^^^^^^

    ::

        {
          "messages": [
            {
              "myField" : "Custom field myField adjusted to to do"
            },
            {
              "myField_1": "Custom field myField_1 adjusted test (was: to do)"
            },
            {
              "myField_2": "Custom field myField_1 adjusted to done (was: test)"
            }
          ]
        }

    """  # noqa
    output = {'messages': []}
    repo = _get_repo(repo, username, namespace)
    _check_issue_tracker(repo)
    _check_token(repo)

    issue = _get_issue(repo, issueid)
    _check_ticket_access(issue)

    fields = flask.request.form

    if not fields:
        raise pagure.exceptions.APIError(
            400, error_code=APIERROR.EINVALIDREQ)

    repo_fields = {k.name: k for k in repo.issue_keys}

    if not all(key in repo_fields.keys() for key in fields.keys()):
        raise pagure.exceptions.APIError(
            400, error_code=APIERROR.EINVALIDISSUEFIELD)

    for field in fields:
        key = repo_fields[field]
        value = fields.get(key.name)
        if value:
            _check_link_custom_field(key, value)
        try:
            message = pagure.lib.set_custom_key_value(
                SESSION, issue, key, value)

            SESSION.commit()
            if message:
                output['messages'].append({key.name: message})
                pagure.lib.add_metadata_update_notif(
                    session=SESSION,
                    obj=issue,
                    messages=message,
                    user=flask.g.fas_user.username,
                    gitfolder=APP.config['TICKETS_FOLDER']
                )
            else:
                output['messages'].append({key.name: 'No changes'})
        except pagure.exceptions.PagureException as err:
            raise pagure.exceptions.APIError(
                400, error_code=APIERROR.ENOCODE, error=str(err))
        except SQLAlchemyError as err:  # pragma: no cover
            print(err)
            SESSION.rollback()
            raise pagure.exceptions.APIError(400, error_code=APIERROR.EDBERROR)

    jsonout = flask.jsonify(output)
    return jsonout


@API.route('/<repo>/issues/history/stats')
@API.route('/<namespace>/<repo>/issues/history/stats')
@API.route('/fork/<username>/<repo>/issues/history/stats')
@API.route('/fork/<username>/<namespace>/<repo>/issues/history/stats')
@api_method
def api_view_issues_history_stats(repo, username=None, namespace=None):
    """
    List project's statistical issues history.
    ------------------------------------------
    Provides the number of opened issues over the last 6 months of the
    project.

    ::

        GET /api/0/<repo>/issues/history/stats
        GET /api/0/<namespace>/<repo>/issues/history/stats

    ::

        GET /api/0/fork/<username>/<repo>/issues/history/stats
        GET /api/0/fork/<username>/<namespace>/<repo>/issues/history/stats


    Sample response
    ^^^^^^^^^^^^^^^

    ::

        {
          "stats": {
            ...
            "2017-09-19T13:10:51.041345": 6,
            "2017-09-26T13:10:51.041345": 6,
            "2017-10-03T13:10:51.041345": 6,
            "2017-10-10T13:10:51.041345": 6,
            "2017-10-17T13:10:51.041345": 6
          }
        }

    """
    repo = _get_repo(repo, username, namespace)
    _check_issue_tracker(repo)

    stats = pagure.lib.issues_history_stats(SESSION, repo)
    jsonout = flask.jsonify({'stats': stats})
    return jsonout
