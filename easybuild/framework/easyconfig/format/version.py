# #
# Copyright 2013-2013 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be/nl/en),
# the Hercules foundation (http://www.herculesstichting.be/in_English)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# http://github.com/hpcugent/easybuild
#
# EasyBuild is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation v2.
#
# EasyBuild is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with EasyBuild.  If not, see <http://www.gnu.org/licenses/>.
# #

"""
This describes the easyconfig version class. To be used in easybuild for anythin related to version checking

@author: Stijn De Weirdt (Ghent University)
"""

import operator as op
import re
from distutils.version import LooseVersion
from vsc import fancylogger

from easybuild.tools.toolchain.utilities import search_toolchain


class EasyVersion(LooseVersion):
    """Exact LooseVersion. No modifications needed (yet)"""
    # TODO: replace all LooseVersion with EasyVersion in eb, after moving EasyVersion to easybuild/tools?

    def __len__(self):
        """Determine length of this EasyVersion instance."""
        return len(self.version)


class VersionOperator(object):
    """
    VersionOperator class represent a version expression that includes an operator.

    Supports ordered list of versions, ordering according to operator
    Ordering is highest first, is such that versions[idx] >= versions[idx+1]
    """

    SEPARATOR = '_'
    OPERATOR = {
        '==': op.eq,
        '>': op.gt,
        '>=': op.ge,
        '<': op.lt,
        '<=': op.le,
        '!=': op.ne,
    }

    def __init__(self, txt=None):
        """Initialise.
            @param txt: intialise with txt
        """
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)
        self.regexp = self._operator_regexp()

        self.versions = []

        if txt is not None:
            self.add(txt)

    def _operator_regexp(self, begin_end=True):
        """
        Create the version regular expression with operator support. Support for version indications like
            5_> (anything strict larger then 5)
            @param begin_end: boolean, create a regexp with begin/end match
        """
        # construct escaped operator symbols, e.g. '\<\='
        ops = []
        for op in self.OPERATOR.keys():
            ops.append(re.sub(r'(.)', r'\\\1', op))

        # regexp to parse version expression
        # - ver_str should start/end with any word character except separator
        # - minimal ver_str length is 1
        # - operator part at the end is optional
        reg_text = r"(?P<ver_str>[^%(sep)s\W](?:\S*[^%(sep)s\W])?)(?:%(sep)s(?P<operator>%(ops)s))?" % {
            'sep': self.SEPARATOR,
            'ops': '|'.join(ops),
        }
        if begin_end:
            reg_text = r"^%s$" % reg_text
        reg = re.compile(reg_text)

        self.log.debug("version_operator pattern '%s' (begin_end: %s)" % (reg.pattern, begin_end))
        return reg

    def _convert(self, ver_str):
        """Convert string to EasyVersion instance that can be compared"""
        if ver_str is None:
            ver_str = '0.0.0'
            self.log.warning('_convert: no version passed, set it to %s' % ver_str)
        try:
            version = EasyVersion(ver_str)
        except (AttributeError, ValueError), err:
            self.log.error('Failed to convert %s to an EasyVersion instance: %s' % (ver_str, err))

        self.log.debug('converted string %s to version %s' % (ver_str, version))
        return version

    def _operator_check(self, ver_str=None, operator='=='):
        """
        Return function that functions as a check against version and operator
            @param ver_str: string, sort-of mandatory
            @param oper: string, default to ==
        No positional args to allow **reg.search(txt).groupdict()
        """
        version = self._convert(ver_str)

        if operator in self.OPERATOR:
            op = self.OPERATOR[operator]
        else:
            self.log.error('Failed to match specified operator %s to operator function' % operator)

        def check(test_ver_str):
            """The check function; test version is always the second arg in comparing"""
            test_ver = self._convert(test_ver_str)
            res = op(version, test_ver)
            self.log.debug('Check %s version %s using operator %s: %s' % (version, test_ver, op, res))
            return res

        return check

    def match(self, ver_str):
        """
        See if argument matches a version operator
        If so, return dict with version, operator and check
        """
        res = self.regexp.search(ver_str)
        if not res:
            self.log.error('No version_match for version expression %s' % ver_str)
            return None

        ver_dict = res.groupdict()
        ver_dict['ver_str'] = ver_str
        ver_dict['check_fn'] = self._operator_check(**ver_dict)
        ver_dict['easyversion'] = self._convert(ver_dict['ver_str'])
        self.log.debug('version_match for version expression %s: %s' % (ver_str, ver_dict))
        return ver_dict

    def add(self, txt):
        """
        Add version to ordered list of versions
            Ordering is highest first, is such that version[idx] >= version[idx+1]
            @param txt: text to match
        Build easyconfig with most recent (=most important) first
        """
        version_dict = self.match(txt)
        if version_dict is None:
            msg = 'version %s does not version_match' % txt
            self.log.error(msg)
        else:
            insert_idx = 0
            for idx, v_dict in enumerate(self.versions):
                if self.OPERATOR['<'](version_dict['easyversion'], v_dict['easyversion']):
                    self.log.debug('Found version %s (idx %s) < then new to add %s' %
                                   (v_dict['easyversion'], idx, version_dict['easyversion']))
                    insert_idx = idx
                    break
            self.log.debug('Insert version %s in index %s' % (version_dict, insert_idx))
            self.versions.insert(insert_idx, version_dict)

class ToolchainOperator(object):
    """Dict with toolchains and versionoperator instance"""
    SEPARATOR = '_'

    def __init__(self):
        """Initialise"""
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)
        self.regexp = self._operator_regexp()

    def _operator_regexp(self):
        """
        Create the regular expression for toolchain support of format
            ^toolchain_version$
        with toolchain one of the supported toolchains and version in version_operator syntax
        """
        _, all_tcs = search_toolchain('')
        tc_names = [x.NAME for x in all_tcs]
        self.log.debug("found toolchain names %s " % (tc_names))

        vop = VersionOperator()
        vop_pattern = vop._operator_regexp(begin_end=False).pattern
        toolchains = r'(%s)' % '|'.join(tc_names)
        toolchain_reg = re.compile(r'^(?P<toolchainname>%s)(?:%s(?P<toolchainversion>%s))?$' %
                                   (toolchains, self.SEPARATOR, vop_pattern))

        self.log.debug("toolchain_operator pattern %s " % (toolchain_reg))
        return toolchain_reg

    def toolchain_match(self, txt):
        """
        See if txt matches a toolchain_operator
        If so, return dict with tcname and optional version, operator and check
        """
        r = self.toolchain_regexp.search(txt)
        if not r:
            self.log.error('No toolchain_match for txt %s' % txt)
            return None

        res = r.groupdict()
        res['txt'] = txt
        versiontxt = res.get('toolchainversion', None)
        if versiontxt is None:
            self.log.debug('No toolchainversion specified in txt %s (%s)' % (txt, res))
        else:
            vop = VersionOperator()
            res['check_fn'] = vop._operator_check(version=res['version'], oper=res['operator'])
        self.log.debug('toolchain_match for txt %s: %s' % (txt, res))
        return res


class ConfigObjVersion(object):
    """
    ConfigObj version checker
    - first level sections except default
      - check toolchain
      - check version
    - second level
      - version : dependencies

    Given ConfigObj instance, make instance that can check if toolchain/version is allowed,
        return version / toolchain / toolchainversion and dependency

    Mandatory (to fake v1.0 behaviour)? Set this eb wide through other config file?
    [DEFAULT]
    version=version_operator
    toolchain=toolchain_operator
    Optional
    [DEFAULT]
    [[SUPPORTED]]
    toolchains=toolchain_operator,...
    versions=version_operator,...
    [versionX_operator]
    [versionY_operator]
    [toolchainX_operator]
    [toolchainY_operator]
    """

    def __init__(self, configobj=None):
        """
        Initialise.
            @param configobj: ConfigObj instance
        """
        self.log = fancylogger.getLogger(self.__class__.__name__, fname=False)

        self.configobj = None

        if configobj is not None:
            self.set_configobj(configobj)

    def set_configobj(self, configobj):
        """
        Set the configobj
            @param configobj: ConfigObj instance
        """
        for name, section in configobj.items():
            if name == 'DEFAULT':
                if 'version' in section:
                    self.add_version(section['version'], section=name)
                if 'toolchain' in section:
                    toolchain = self.toolchain_match(section['toolchain'])
                    if toolchain is None:
                        self.log.error('Section %s toolchain %s does not toolchain_match' %
                                       (name, section['toolchain']))
            else:
                toolchain = self.add_toolchain(name, section=name, error=False)
                if toolchain is None:
                    version = self.add_version(name, section=name, error=False)
                    if version is None:
                        self.log.debug('Name %s section %s no version nor toolchain' % (name, section))
