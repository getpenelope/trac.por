# -*- coding: utf-8 -*-

import pkg_resources

from trac.util.translation import domain_functions, add_domain


_, tag_, N_, add_tracpor_domain = \
            domain_functions('trac.por', ('_', 'tag_', 'N_', 'add_domain'))


def add_domains(env_path):
    locale_dir = pkg_resources.resource_filename(__name__, 'locale')
    add_tracpor_domain(env_path, locale_dir)

