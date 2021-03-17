#!/usr/bin/python

from __future__ import absolute_import, division, print_function
__metaclass__ = type

from time import sleep
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.six.moves import xmlrpc_client


class ActionNotSupported(Exception):
    '''Action is not supported'''
    def __init__(self, message='Action is not supported'):
        super(ActionNotSupported, self).__init__()
        self.msg = message

    def __str__(self):
        return repr(self.msg)


class ParameterMissing(Exception):
    '''Required parameter missing'''
    def __init__(self, param_name):
        super(ParameterMissing, self).__init__()
        self.msg = "Required parameter missing: %s" % param_name

    def __str__(self):
        return repr(self.msg)


class Cobbler(AnsibleModule):
    '''Ansible module to operate Cobbler via XML-RPC'''

    default_url = 'http://localhost/cobbler_api'

    module_arguments = dict(
        username=dict(required=True, no_log=True),
        password=dict(required=True, no_log=True),
        server_url=dict(required=False, default=default_url),
        action=dict(required=True, no_log=False),
        item=dict(required=False, no_log=False, aliases=['entity']),
        params=dict(type='dict', required=False, no_log=True),
        )

    module_result = dict(changed=False)

    def __init__(self):
        super(Cobbler, self).__init__(argument_spec=self.module_arguments)

        self.server = None
        self.token = None

    def exit_fail(self, message):
        '''Fail with error message'''
        self.fail_json(msg=message)

    def exit(self, **result):
        '''Module exit'''
        self.server.logout(self.token)
        self.module_result.update(result)
        self.exit_json(**self.module_result)

    def credentials(self):
        '''Return tuple of username and password'''
        username = self.params['username']
        password = self.params['password']

        return (username, password)

    def connect(self, url):
        '''Connect to the Cobbler server'''
        try:
            self.server = xmlrpc_client.Server(url)
            self.server.ping()
        except Exception as error:
            self.exit_fail('Cannot connect to %s: %s' % (url, str(error)))

        self.log('Successfully connected to %s' % url)

    def authenticate(self, username, password):
        '''Authenticate to the Cobbler server'''
        try:
            self.token = self.server.login(username, password)
        except Exception as error:
            self.exit_fail('Authentication failed: %s' % str(error))

        self.log('Authentication successfull')

    def connect_to_cobbler(self):
        '''Connect and authenticate to the Cobbler server'''
        url = self.params['server_url']

        self.connect(url)
        self.authenticate(*self.credentials())

    def dispatch_action(self, action=None):
        '''Dispatch function to call by action'''
        if action is None:
            action = self.params['action']

        dispatch = {
            'has': self.has_item,
            'get': self.get_item,
            'add': self.add_item,
            'new': self.add_item,
            'copy': self.copy_item,
            'rename': self.rename_item,
            'modify': self.modify_item,
            'change': self.modify_item,
            'remove': self.remove_item,
            'delete': self.remove_item,
            'del': self.remove_item,
            'list': self.get_item_names,
            'sync': self.sync,
            'reposync': self.reposync,
            'import': self.background_import,
            }

        return dispatch.get(action, None)

    def has_item(self):
        '''Execute xmlrpc call for has_item'''
        item = self.params['item']
        params = self.params['params']
        name = params.get('name')
        token = self.token

        if name is None:
            raise ParameterMissing('name')

        if self.server.has_item(item, name, token):
            msg = '%s exists' % item
            return dict(changed=False, msg=msg, has=True, exists=True)

        msg = '%s does not exist' % item
        return dict(changed=False, msg=msg, has=False, exists=False)

    def get_item(self):
        '''Execute xmlrpc call for get_item'''
        item = self.params['item']
        params = self.params['params']
        name = params.get('name')
        token = self.token

        if name is None:
            raise ParameterMissing('name')

        result = self.server.get_item(item, name, token)

        if not isinstance(result, dict):
            msg = '%s does not exist' % item
            return dict(changed=False, rc=1, msg=msg, result=result)

        return dict(changed=False, result=result)

    def get_item_names(self):
        '''Execute xmlrpc call for get_item_names'''
        item = self.params['item']
        results = self.server.get_item_names(item)

        if not isinstance(results, list):
            msg = 'Could not get list for %ss' % item
            return dict(changed=False, rc=1, msg=msg, results=results)

        return dict(changed=False, results=results)

    def add_item(self):
        '''Execute xmlrpc call for add_item'''
        item = self.params['item']
        params = self.params['params']
        name = params.get('name')
        token = self.token

        if name is None:
            raise ParameterMissing('name')

        if self.has_item()['exists'] is True:
            msg = '%s already exists' % (item)
            return dict(changed=False, msg=msg)

        handle = self.server.new_item(item, token)
        self.server.modify_item(item, handle, 'name', name, token)

        for param in params:
            if item == "system" and param == "interfaces":
                self.server.modify_item(item, handle, "modify_interface",
                                        params[param], token)
            else:
                self.server.modify_item(item, handle, param,
                                        params[param], token)

        success = self.server.save_item(item, handle, token)

        if success:
            msg = '%s has been added' % (item)
            return dict(changed=True, msg=msg, status=success)

        msg = 'could not add %s' % (item)
        return dict(changed=False, rc=1, msg=msg, status=success)

    def copy_item(self):
        '''Execute xmlrpc call for copy_item'''
        item = self.params['item']
        params = self.params['params']
        name = params.get('name')
        new_name = params.get('new_name')
        token = self.token

        if name is None:
            raise ParameterMissing('name')
        if new_name is None:
            raise ParameterMissing('new_name')

        if self.has_item()['exists'] is not True:
            msg = '%s does not exist' % (item)
            return dict(changed=False, rc=1, msg=msg)

        handle = self.server.get_item_handle(item, name, token)
        success = self.server.copy_item(item, handle, new_name, token)

        if success is True:
            msg = '%s has been copied' % (item)
            return dict(changed=True, msg=msg, status=success)

        msg = 'could not copy %s' % (item)
        return dict(changed=False, rc=1, msg=msg, status=success)

    def rename_item(self):
        '''Execute xmlrpc call for rename_item'''
        item = self.params['item']
        params = self.params['params']
        name = params.get('name')
        new_name = params.get('new_name')
        token = self.token

        if name is None:
            raise ParameterMissing('name')
        if new_name is None:
            raise ParameterMissing('new_name')

        if self.has_item()['exists'] is not True:
            msg = '%s does not exist' % (item)
            return dict(changed=False, rc=1, msg=msg)

        handle = self.server.get_item_handle(item, name, token)
        success = self.server.rename_item(item, handle, new_name, token)

        if success:
            msg = '%s has been renamed' % (item)
            return dict(changed=True, msg=msg, status=success)

        msg = 'could not rename %s' % (item)
        return dict(changed=False, rc=1, msg=msg, status=success)

    def remove_item(self):
        '''Execute xmlrpc call for remove_item'''
        item = self.params['item']
        params = self.params['params']
        name = params.get('name')
        token = self.token

        if name is None:
            raise ParameterMissing('name')

        if self.has_item()['exists'] is not True:
            msg = '%s does not exist' % (item)
            return dict(changed=False, rc=1, msg=msg)

        success = self.server.remove_item(item, name, token)

        if success:
            msg = '%s has been removed' % (item)
            return dict(changed=True, msg=msg, status=success)

        msg = 'could not remove %s' % (item)
        return dict(changed=False, rc=1, msg=msg, status=success)

    def modify_item(self):
        '''Execute xmlrpc call for modify_item'''
        item = self.params['item']
        params = self.params['params']
        name = params.get('name')
        token = self.token

        if name is None:
            raise ParameterMissing('name')

        if self.has_item()['exists'] is True:
            handle = self.server.get_item_handle(item, name, token)
        else:
            handle = self.server.new_item(item, token)

        for param in params:
            if item == "system" and param == "interfaces":
                self.server.modify_item(item, handle, "modify_interface",
                                        params[param], token)
            else:
                self.server.modify_item(item, handle, param,
                                        params[param], token)

        success = self.server.save_item(item, handle, token)

        if success:
            msg = '%s has been modified' % (item)
            return dict(changed=True, msg=msg, status=success)

        msg = 'could not modify %s' % (item)
        return dict(changed=False, rc=1, msg=msg, status=success)

    def sync(self):
        '''Execute xmlrpc call for sync'''
        token = self.token

        success = self.server.sync(token)

        if success:
            msg = 'sync successfull'
            return dict(changed=True, msg=msg, status=success)

        msg = 'sync has not been successfull'
        return dict(changed=False, rc=1, msg=msg, status=success)

    def reposync(self):
        '''Execute xmlrpc call for background_reposync'''
        params = self.params['params']
        token = self.token

        if params is None:
            params = {}

        task_id = self.server.background_reposync(params, token)
        status = self.wait_event_finished(task_id)
        status_msg = status[2]

        if status_msg == 'success':
            msg = 'repository sync successfull'
            return dict(changed=True, msg=msg, status=status)

        msg = 'repository sync has not been successfull'
        return dict(changed=False, rc=1, msg=msg, status=status)

    def background_import(self):
        '''Execute xmlrpc call for background_import'''
        params = self.params['params']
        token = self.token

        if params is None:
            params = {}

        task_id = self.server.background_import(params, token)
        status = self.wait_event_finished(task_id)
        status_msg = status[2]

        if status_msg == 'complete':
            msg = 'import successfull'
            return dict(changed=True, msg=msg, status=status)

        msg = 'import has not been successfull'
        return dict(changed=False, rc=1, msg=msg, status=status)

    def wait_event_finished(self, event_id):
        '''Poll event status and return status when finished'''
        while True:
            status = self.server.get_task_status(event_id)
            status_msg = status[2]

            if status_msg != "running":
                break

            sleep(2)

        return status


def main():
    '''Run the module'''
    cobbler = Cobbler()
    try:
        cobbler.connect_to_cobbler()
        action_func = cobbler.dispatch_action()

        if action_func is None:
            raise ActionNotSupported

        result = action_func()
    except Exception as error:
        cobbler.exit_fail(str(error))

    cobbler.exit(**result)


if __name__ == '__main__':
    main()
