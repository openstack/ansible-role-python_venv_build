========================
Team and repository tags
========================

.. image:: https://governance.openstack.org/tc/badges/openstack-ansible-python_venv_build.svg
    :target: https://governance.openstack.org/tc/reference/tags/index.html

.. Change things from this point on

===================================
OpenStack-Ansible python_venv_build
===================================

This Ansible role prepares a python venv for use in OpenStack-Ansible.

The role requires the following to be present prior to execution:

* virtualenv >= 1.10 (to support using the never-download option)
* pip >= 7.1 (to support using the constraints option) in the virtualenv
  once it has been created.

Use-cases
~~~~~~~~~

This role is built to cater to the following use-cases:

# Execute a build against a build host, then serve the venvs from a web
  server.
# Execute a build against the first host in a group, then serving the
  venvs from the deployment host.

References
~~~~~~~~~~

Documentation for the project can be found at:
  https://docs.openstack.org/ansible-role-python_venv_build/latest/

The project home is at:
  http://launchpad.net/openstack-ansible

Release notes for the project can be found at:
  https://docs.openstack.org/releasenotes/ansible-role-python_venv_build/
