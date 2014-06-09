'''This is a collection of helper functions for use in tests.

We want to avoid sharing test helper functions between test modules as
much as possible, and we definitely don't want to share test fixtures between
test modules, or to introduce a complex hierarchy of test class subclasses,
etc.

We want to reduce the amount of "travel" that a reader needs to undertake to
understand a test method -- reducing the number of other files they need to go
and read to understand what the test code does. And we want to avoid tightly
coupling test modules to each other by having them share code.

But some test helper functions just increase the readability of tests so much
and make writing tests so much easier, that it's worth having them despite the
potential drawbacks.

This module is reserved for these very useful functions.

'''
import os

import webtest
import pylons.config as config

import ckan.config.middleware
import ckan.model as model
import ckan.logic as logic


def reset_db():
    '''Reset CKAN's database.

    If a test class uses the database, then it should call this function in its
    ``setup()`` method to make sure that it has a clean database to start with
    (nothing left over from other test classes or from previous test runs).

    If a test class doesn't use the database (and most test classes shouldn't
    need to) then it doesn't need to call this function.

    :returns: ``None``

    '''
    # Close any database connections that have been left open.
    # This prevents CKAN from hanging waiting for some unclosed connection.
    model.Session.close_all()

    model.repo.rebuild_db()


def call_action(action_name, context=None, **kwargs):
    '''Call the named ``ckan.logic.action`` function and return the result.

    This is just a nicer way for user code to call action functions, nicer than
    either calling the action function directly or via
    :py:func:`ckan.logic.get_action`.

    For example::

        user_dict = call_action('user_create', name='seanh',
                                email='seanh@seanh.com', password='pass')

    Any keyword arguments given will be wrapped in a dict and passed to the
    action function as its ``data_dict`` argument.

    Note: this skips authorization! It passes 'ignore_auth': True to action
    functions in their ``context`` dicts, so the corresponding authorization
    functions will not be run.
    This is because ckan.new_tests.logic.action tests only the actions, the
    authorization functions are tested separately in
    ckan.new_tests.logic.auth.
    See the :doc:`testing guidelines </contributing/testing>` for more info.

    This function should eventually be moved to
    :py:func:`ckan.logic.call_action` and the current
    :py:func:`ckan.logic.get_action` function should be
    deprecated. The tests may still need their own wrapper function for
    :py:func:`ckan.logic.call_action`, e.g. to insert ``'ignore_auth': True``
    into the ``context`` dict.

    :param action_name: the name of the action function to call, e.g.
        ``'user_update'``
    :type action_name: string
    :param context: the context dict to pass to the action function
        (optional, if no context is given a default one will be supplied)
    :type context: dict
    :returns: the dict or other value that the action function returns

    '''
    if context is None:
        context = {}
    context.setdefault('user', '127.0.0.1')
    context.setdefault('ignore_auth', True)
    return logic.get_action(action_name)(context=context, data_dict=kwargs)


def call_auth(auth_name, context, **kwargs):
    '''Call the named ``ckan.logic.auth`` function and return the result.

    This is just a convenience function for tests in
    :py:mod:`ckan.new_tests.logic.auth` to use.

    Usage::

        result = helpers.call_auth('user_update', context=context,
                                   id='some_user_id',
                                   name='updated_user_name')

    :param auth_name: the name of the auth function to call, e.g.
        ``'user_update'``
    :type auth_name: string

    :param context: the context dict to pass to the auth function, must
        contain ``'user'`` and ``'model'`` keys,
        e.g. ``{'user': 'fred', 'model': my_mock_model_object}``
    :type context: dict

    :returns: the dict that the auth function returns, e.g.
        ``{'success': True}`` or ``{'success': False, msg: '...'}``
        or just ``{'success': False}``
    :rtype: dict

    '''
    import ckan.logic.auth.update

    assert 'user' in context, ('Test methods must put a user name in the '
                               'context dict')
    assert 'model' in context, ('Test methods must put a model in the '
                                'context dict')

    # FIXME: Do we want to go through check_access() here?
    auth_function = ckan.logic.auth.update.__getattribute__(auth_name)
    return auth_function(context=context, data_dict=kwargs)


def _get_test_app():
    '''Return a webtest.TestApp for CKAN, with legacy templates disabled.

    For functional tests that need to request CKAN pages or post to the API.
    Unit tests shouldn't need this.

    '''
    config['ckan.legacy_templates'] = False
    app = ckan.config.middleware.make_app(config['global_conf'], **config)
    app = webtest.TestApp(app)
    return app


class FunctionalTestBaseClass():
    '''A base class for functional test classes to inherit from.

    Allows configuration changes by overriding _apply_config_changes and
    resetting the CKAN config after your test class has run. It creates a
    webtest.TestApp at self.app for your class to use to make HTTP requests
    to the CKAN web UI or API.

    If you're overriding methods that this class provides, like setup_class()
    and teardown_class(), make sure to use super() to call this class's methods
    at the top of yours!

    '''
    @classmethod
    def setup_class(cls):
        # Make a copy of the Pylons config, so we can restore it in teardown.
        cls.original_config = config.copy()
        cls._apply_config_changes(config)
        cls.app = _get_test_app()

    @classmethod
    def _apply_config_changes(cls, cfg):
        pass

    def setup(self):
        import ckan.model as model
        model.Session.close_all()
        model.repo.rebuild_db()

    @classmethod
    def teardown_class(cls):
        # Restore the Pylons config to its original values, in case any tests
        # changed any config settings.
        config.clear()
        config.update(cls.original_config)


## FIXME: remove webtest_* functions below when we upgrade webtest

def webtest_submit(form, name=None, index=None, value=None, **args):
    '''
    backported version of webtest.Form.submit that actually works
    for submitting with different submit buttons.

    We're stuck on an old version of webtest because we're stuck
    on an old version of webob because we're stuck on an old version
    of Pylons. This prolongs our suffering, but on the bright side
    it lets us have functional tests that work.
    '''
    fields = webtest_submit_fields(form, name, index=index, submit_value=value)
    if form.method.upper() != "GET":
        args.setdefault("content_type",  form.enctype)
    return form.response.goto(form.action, method=form.method,
        params=fields, **args)

def webtest_submit_fields(form, name=None, index=None, submit_value=None):
    '''
    backported version of webtest.Form.submit_fields that actually works
    for submitting with different submit buttons.
    '''
    from webtest.app import File
    submit = []
    # Use another name here so we can keep function param the same for BWC.
    submit_name = name
    if index is not None and submit_value is not None:
        raise ValueError("Can't specify both submit_value and index.")

    # If no particular button was selected, use the first one
    if index is None and submit_value is None:
        index = 0

    # This counts all fields with the submit name not just submit fields.
    current_index = 0
    for name, field in form.field_order:
        if name is None:  # pragma: no cover
            continue
        if submit_name is not None and name == submit_name:
            if index is not None and current_index == index:
                submit.append((name, field.value_if_submitted()))
            if submit_value is not None and \
               field.value_if_submitted() == submit_value:
                submit.append((name, field.value_if_submitted()))
            current_index += 1
        else:
            value = field.value
            if value is None:
                continue
            if isinstance(field, File):
                submit.append((name, field))
                continue
            if isinstance(value, list):
                for item in value:
                    submit.append((name, item))
            else:
                submit.append((name, value))
    return submit
