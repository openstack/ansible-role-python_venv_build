#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright 2026, Cleura AB
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import glob
import hashlib
import os
import re
import shlex
import shutil
import tempfile

from ansible.module_utils.basic import AnsibleModule

__metaclass__ = type

DOCUMENTATION = r'''
---
module: pep503_wheel_build
short_description: Build python wheels and generate PEP 503 simple repository
description:
  - Invokes pip wheel for given requirements and constraints into a temporary
    directory.
  - Moves built wheels to the central wheel directory.
  - Canonicalizes package names according to PEP 503 and creates directory
    structure with symlinks.
  - Returns structured facts including normalized constraints for venv
    installation.
options:
  virtualenv:
    description: Path to builder virtualenv containing pip.
    required: true
    type: path
  requirements_file:
    description: Path to requirements.txt file.
    required: true
    type: path
  global_constraints_file:
    description: Path to global constraints file.
    required: false
    type: path
  source_constraints_file:
    description: Path to source constraints file.
    required: false
    type: path
  wheel_dir:
    description: Path to central wheel storage directory.
    required: true
    type: path
  index_url:
    description: Base URL to pass to pip --index-url.
    required: false
    type: str
  trusted_host:
    description: Hostname to pass to pip --trusted-host.
    required: false
    type: str
  log_file:
    description: Path to log file for pip wheel output.
    required: false
    type: path
  build_args:
    description: Extra arguments string to pass to pip wheel.
    required: false
    type: str
    default: ''
  owner:
    description: User name or UID to set as owner on created files and
      directories.
    required: false
    type: str
  group:
    description: Group name or GID to set as group on created files and
      directories.
    required: false
    type: str
'''

EXAMPLES = r'''
- name: Build wheels and index
  pep503_wheel_build:
    virtualenv: /openstack/venvs/wheel-builder
    requirements_file: /var/www/repo/.../keystone-requirements.txt
    wheel_dir: /var/www/repo/.../wheels
    index_url: http://localhost:8181/os-releases/.../simple/
'''

RETURN = r'''
wheels:
  description: List of wheel filenames moved into wheel_dir.
  type: list
  returned: success
constraints:
  description: List of normalized package constraints (e.g. name==version).
  type: list
  returned: success
'''


def normalize_pep503(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def parse_wheel_constraint(filename):
    parts = filename.split('-')
    dist_name = parts[0]
    pkg_name = normalize_pep503(dist_name)
    version = parts[1].replace('_', '.post').lower()
    return f"{pkg_name}=={version}"


def calculate_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def update_package_index_html(pkg_dir, pkg_name, owner=None, group=None):
    wheel_files = sorted(
        [f for f in os.listdir(pkg_dir) if f.endswith('.whl')]
    )
    links = []
    for w in wheel_files:
        w_path = os.path.join(pkg_dir, w)
        digest = calculate_sha256(w_path)
        links.append(f'    <a href="{w}#sha256={digest}">{w}</a><br/>')

    links_html = '\n'.join(links)
    html_content = f"""<!DOCTYPE html>
<html>
  <head><title>Links for {pkg_name}</title></head>
  <body>
    <h1>Links for {pkg_name}</h1>
{links_html}
  </body>
</html>
"""
    index_file = os.path.join(pkg_dir, 'index.html')
    with open(index_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    set_ownership(index_file, owner, group)


def update_root_simple_index_html(simple_dir, owner=None, group=None):
    packages = sorted([
        d for d in os.listdir(simple_dir)
        if os.path.isdir(os.path.join(simple_dir, d)) and not d.startswith('.')
    ])
    links = [f'    <a href="{p}/">{p}</a><br/>' for p in packages]
    links_html = '\n'.join(links)
    html_content = f"""<!DOCTYPE html>
<html>
  <head><title>Simple Index</title></head>
  <body>
    <h1>Simple Index</h1>
{links_html}
  </body>
</html>
"""
    root_index = os.path.join(simple_dir, 'index.html')
    with open(root_index, 'w', encoding='utf-8') as f:
        f.write(html_content)
    set_ownership(root_index, owner, group)


def set_ownership(path, owner=None, group=None):
    if not owner and not group:
        return
    try:
        shutil.chown(path, user=owner, group=group)
    except Exception:
        pass


def run_module():
    module_args = dict(
        virtualenv=dict(type='path', required=True),
        requirements_file=dict(type='path', required=True),
        global_constraints_file=dict(
            type='path', required=False, default=None
        ),
        source_constraints_file=dict(
            type='path', required=False, default=None
        ),
        wheel_dir=dict(type='path', required=True),
        index_url=dict(type='str', required=False, default=None),
        trusted_host=dict(type='str', required=False, default=None),
        log_file=dict(type='path', required=False, default=None),
        build_args=dict(type='str', required=False, default=''),
        owner=dict(type='str', required=False, default=None),
        group=dict(type='str', required=False, default=None),
    )

    result = dict(
        changed=False,
        wheels=[],
        constraints=[],
        cmd=[],
        stdout='',
        stderr='',
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=False,
    )

    virtualenv = module.params['virtualenv']
    pip_executable = os.path.join(virtualenv, 'bin', 'pip')
    requirements_file = module.params['requirements_file']
    global_constraints_file = module.params['global_constraints_file']
    source_constraints_file = module.params['source_constraints_file']
    wheel_dir = os.path.abspath(module.params['wheel_dir'])
    simple_dir = os.path.join(os.path.dirname(wheel_dir), 'simple')
    index_url = module.params['index_url']
    trusted_host = module.params['trusted_host']
    log_file = module.params['log_file']
    build_args = module.params['build_args']
    owner = module.params['owner']
    group = module.params['group']

    if not os.path.exists(pip_executable):
        module.fail_json(
            msg=f"Pip executable not found: {pip_executable}",
            **result
        )

    if not os.path.exists(requirements_file):
        module.fail_json(
            msg=f"Requirements file not found: {requirements_file}",
            **result
        )

    temp_dir = tempfile.mkdtemp(prefix='ansible-wheel-build-')
    set_ownership(temp_dir, owner, group)

    try:
        cmd = [
            pip_executable,
            'wheel',
            '--requirement', requirements_file,
            '--wheel-dir', temp_dir,
        ]

        if global_constraints_file and os.path.exists(global_constraints_file):
            cmd.extend(['--constraint', global_constraints_file])

        if source_constraints_file and os.path.exists(source_constraints_file):
            cmd.extend(['--constraint', source_constraints_file])

        if wheel_dir:
            cmd.extend(['--find-links', f"{wheel_dir}/"])

        if index_url:
            cmd.extend(['--index-url', index_url])

        if trusted_host:
            cmd.extend(['--trusted-host', trusted_host])

        if log_file:
            cmd.extend(['--log', log_file])

        if build_args:
            cmd.extend(shlex.split(build_args))

        result['cmd'] = cmd

        # Run pip wheel
        rc, stdout, stderr = module.run_command(cmd)
        result['rc'] = rc
        result['stdout'] = stdout
        result['stderr'] = stderr

        if rc != 0:
            module.fail_json(msg="pip wheel command failed", **result)

        built_wheel_files = glob.glob(os.path.join(temp_dir, '*.whl'))
        if not built_wheel_files:
            module.fail_json(
                msg=f"No wheels were generated in {temp_dir}", **result)

        # Ensure target directories exist
        os.makedirs(wheel_dir, exist_ok=True)
        set_ownership(wheel_dir, owner, group)
        os.makedirs(simple_dir, exist_ok=True)
        set_ownership(simple_dir, owner, group)

        wheels_list = []
        constraints_list = []
        affected_packages = set()

        for wheel_path in sorted(built_wheel_files):
            filename = os.path.basename(wheel_path)
            dest_wheel_path = os.path.join(wheel_dir, filename)

            # Move wheel to central wheels directory
            shutil.move(wheel_path, dest_wheel_path)
            set_ownership(dest_wheel_path, owner, group)

            # Canonicalize package name and create simple directory structure
            dist_name = filename.split('-')[0]
            canonical_name = normalize_pep503(dist_name)
            pkg_dir = os.path.join(simple_dir, canonical_name)
            os.makedirs(pkg_dir, exist_ok=True)
            set_ownership(pkg_dir, owner, group)

            # Create relative symlink
            symlink_path = os.path.join(pkg_dir, filename)
            rel_target = os.path.relpath(dest_wheel_path, pkg_dir)

            if os.path.islink(symlink_path) or os.path.exists(symlink_path):
                os.remove(symlink_path)
            os.symlink(rel_target, symlink_path)

            wheels_list.append(filename)
            constraints_list.append(parse_wheel_constraint(filename))
            affected_packages.add(canonical_name)

        if wheels_list:
            # Generate index.html for all affected package directories
            for canonical_name in sorted(affected_packages):
                pkg_dir = os.path.join(simple_dir, canonical_name)
                update_package_index_html(pkg_dir, canonical_name,
                                          owner, group)

            # Update root /simple/index.html
            update_root_simple_index_html(simple_dir, owner, group)

        result['changed'] = len(wheels_list) > 0
        result['wheels'] = wheels_list
        result['constraints'] = constraints_list
        module.exit_json(**result)

    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    run_module()


if __name__ == '__main__':
    main()
