#!/usr/bin/env python3
#
# Copyright (c) Gao Wang, Stephens Lab at The Univeristy of Chicago
# Distributed under the terms of the MIT License.

import os
import subprocess
import unittest

from dsc.dsc_parser import DSC_Script
from dsc.utils import FormatError

text0 = '''
DSC:
    run: simulate
'''
text1 = text0 + '''
simulate: R(), R()
    x: 1
    y: 2
    $out: x
'''
text2 = text0 + '''
simulate: R()
    group_1:
        x: 1
        y: 2
    $out: x
'''
text3 = text0 + '''
simulate: R()
    @simulate:
        x: 1
        y: 2
    $out: x
'''
text4 = text0 + '''
simulate: R()
    @simulate:
        group_1:
            x: 1
            y: 2
    $x: x
'''
text5 = text0 + '''
simulate: R()
    @simulate:
        x: 1
        y: 2
    @ALIAS:
        x_1: x
    $out: x
'''
text6 = text0 + '''
simulate: R()
    @simulate:
        x: 1
        y: 2
    @ALIAS: 
        simulate: x_1 = x
    $out: x
'''
text7 = text0 + '''
simulate: R()
    @simulate:
        x: 1
        y: 2
        @ALIAS: x_1 = x
    $out: x
'''
class TestParser(unittest.TestCase):
    def setUp(self):
        subprocess.call('sos remove -s', shell=True)
        self.temp_files = []

    def tearDown(self):
        for f in self.temp_files:
            if file_target(f).exists():
                file_target(f).unlink()

    def touch(self, files):
        '''create temporary files'''
        if isinstance(files, str):
            files = [files]
        #
        for f in files:
            with open(f, 'w') as tmp:
                tmp.write('test')
        #
        self.temp_files.extend(files)

    def testBasicSyntaxPass(self):
        '''basic syntax parser success'''
        # exec decoration
        res = DSC_Script(text3)
        self.assertEqual(list(res.modules['simulate'].dump()['input'].items()), [('x', [1]), ('y', [2])])        
        # alias for specific module, both syntax supported
        res = DSC_Script(text6)
        self.assertEqual(list(res.modules['simulate'].dump()['input'].items()), [('x', [1]), ('y', [2])])
        self.assertEqual(list(res.modules['simulate'].plugin.alias_map.items()), [('x', 'x_1')])

    def testBasicSyntaxFail(self):
        '''basic syntax parser fail'''
        # multiple exec output
        # FIXME: test below should fail
        # self.assertRaises(FormatError, DSC_Script, text1)
        # grouped parameters is not allowed
        self.assertRaises(FormatError, DSC_Script, text2)
        # grouped parameters is not allowed in exec decoration
        self.assertRaises(FormatError, DSC_Script, text4)
        # alias is not a list
        self.assertRaises(FormatError, DSC_Script, text5)



        

    def testWorkflows(self):
        '''Test workflows defined in SoS script'''
        script = SoS_Script('''[0]''')
        self.assertEqual(sorted(script.workflows), [''])
        script = SoS_Script('''[0]\n[1]''')
        self.assertEqual(sorted(script.workflows), [''])
        script = SoS_Script('''[0]\n[*_1]''')
        self.assertEqual(sorted(script.workflows), [''])
        script = SoS_Script('''[0]\n[*_1]\n[auxiliary:provides='{a}.txt']''')
        self.assertEqual(sorted(script.workflows), ['', 'auxiliary'])
        script = SoS_Script('''[0]\n[*_1]\n[human_1]''')
        self.assertEqual(sorted(script.workflows), ['', 'human'])
        script = SoS_Script('''[0]\n[*_1]\n[human_1]\n[mouse_2]''')
        self.assertEqual(sorted(script.workflows), [
                         '', 'human', 'mouse'])
        script = SoS_Script('''[0]\n[*_1]\n[human_1]\n[mouse_2]\n[s*_2]''')
        self.assertEqual(sorted(script.workflows), [
                         '', 'human', 'mouse'])
        # unnamed
        script = SoS_Script('''[0]\n[*_1]\n[human_1]\n[mouse]\n[s*_2]''')
        self.assertEqual(sorted(script.workflows), [
                         '', 'human', 'mouse'])
        #
        # workflow name with -
        script = SoS_Script('''[proc-1]\n[test-case_2]''')
        self.assertEqual(sorted(script.workflows), ['proc-1', 'test-case'])
        script.workflow('proc-1')
        script.workflow('proc-1 + test-case:2')

    def testTypeHint(self):
        '''We should be able to differentiate type hint and sos action
        '''
        SoS_Script('''a : list = 5''')
        SoS_Script('''a : list''')
        # action
        SoS_Script('''a : input='filename' ''')
        # action
        SoS_Script('''a : expand='${ }' ''')


    def testSections(self):
        '''Test section definitions'''
        # bad names
        for badname in ['56_1', '_a', 'a_', '1x', '*', '?']:
            self.assertRaises(ParsingError, SoS_Script, '[{}]'.format(badname))
        # bad options
        for badoption in ['ss']:
            self.assertRaises(ParsingError, SoS_Script,
                              '[0:{}]'.format(badoption))
        # allowed names
        for name in ['a5', 'a_5', '*_0', 'a*1_100']:
            SoS_Script('[{}]'.format(name))
        # allowed names with alias
        for name in ['a5 (p1)', 'a_5 (something fun)', '*_0 (no way)', 'a*1_100']:
            SoS_Script('[{}]'.format(name))
        # duplicate sections
        self.assertRaises(ParsingError, SoS_Script,
                          '''[1]\n[1]''')
        self.assertRaises(ParsingError, SoS_Script,
                          '''[1]\n[3]\n[2,1]''')
        self.assertRaises(ParsingError, SoS_Script,
                          '''[a_1]\n[a_3]\n[*_1]''')
        #
        # no duplicated section header
        SoS_Script('''[a_1]\n[a_3]\n[b*_1]''')
        #
        # global section
        self.assertRaises(ParsingError, SoS_Script,
                          '''[global, step_10]''')

    def testGlobalVariables(self):
        '''Test definition of variables'''
        # allow definition
        SoS_Script('''a = '1' ''')
        SoS_Script('''a = ['a', 'b'] ''')
        # but this one has incorrect syntax
        self.assertRaises(ParsingError, SoS_Script,
                          '''a = 'b  ''')
        # This one also does not work because b is not defined.
        #delattr(env, 'sos_dict')
        #script = SoS_Script('''a = b\n[0] ''')
        #wf = script.workflow()
        #dag = Base_Executor(wf).run(mode='dryrun')
        #self.assertRaises(ValueError, Base_Executor(wf).run, dag)
        # multi-line string literal
        SoS_Script('''a = """
this is a multi line
string """
''')
        # multi-line list literal, even with newline in between
        SoS_Script('''a = [
'a',

'b'
]
''')
        #
        SoS_Script(section1_sos)
        # not the default value of 1.0
        #
        script = SoS_Script('''
[global]
a = 1

[b]
print(a)
''')
        wf = script.workflow()
        Base_Executor(wf).run()

    def testParameters(self):
        '''Test parameters section'''
        # directive not allowed in parameters
        script = SoS_Script(section1_sos)
        wf = script.workflow('chapter:0')
        # self.assertRaises(ArgumentError, Base_Executor(wf).run,
        #    args=['--not_exist'])
        # self.assertRaises(ArgumentError, Base_Executor(wf).run,
        #    args=['--par1', 'a', 'b'])
        #
        script = SoS_Script('''
parameter: a = [1, 2]
[0]
''')
        wf = script.workflow()
        self.assertEqual(list(wf.parameters().keys()), ['a'])
        Base_Executor(wf).run()
        self.assertEqual(env.sos_dict['a'], [1, 2])
        env.sos_dict.pop('a')
        wf = script.workflow()
        Base_Executor(wf, args=['--a', '3']).run()
        self.assertEqual(env.sos_dict['a'], [3])
        env.sos_dict.pop('a')
        wf = script.workflow()
        Base_Executor(wf, args=['--a', '3', '5']).run()
        self.assertEqual(env.sos_dict['a'], [3, 5])
        env.sos_dict.pop('a')
        #
        script = SoS_Script('''
# comment
# comment
parameter: a = ['a.txt', 'b.txt']
[0]
''')
        wf = script.workflow()
        Base_Executor(wf).run()
        self.assertEqual(env.sos_dict['a'], ['a.txt', 'b.txt'])
        env.sos_dict.pop('a')
        wf = script.workflow()
        Base_Executor(wf, args=['--a', '3']).run()
        self.assertEqual(env.sos_dict['a'], ['3'])
        env.sos_dict.pop('a')
        wf = script.workflow()
        Base_Executor(wf, args=['--a', '3', '5']).run()
        self.assertEqual(env.sos_dict['a'], ['3', '5'])
        env.sos_dict.pop('a')
        #
        # test parameter using global definition
        script = SoS_Script('''
a="100"

# comment
parameter: b=str(int(a)+1)
[0]
''')
        wf = script.workflow()
        self.assertEqual(list(wf.parameters().keys()), ['b'])
        Base_Executor(wf).run()
        self.assertEqual(env.sos_dict['b'], '101')
        env.sos_dict.pop('b')
        #
        env.sos_dict.clear()
        script = SoS_Script('''
a=100

parameter: b=a+1
[0]
''')
        wf = script.workflow()
        Base_Executor(wf).run()
        self.assertEqual(env.sos_dict['b'], 101)
        env.sos_dict.pop('b')
        #
        script = SoS_Script('''
a=100

parameter: b=a+1.
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--b', '1000']).run()
        #
        self.assertEqual(env.sos_dict['b'], 1000)
        env.sos_dict.pop('b')
        #
        # argument has hve a value
        self.assertRaises(ParsingError, SoS_Script, '''
[0]
parameter: b=

''')
        # if it is a type, must provide value
        script = SoS_Script('''
# comment
parameter: b = int
[0]
''')
        wf = script.workflow()
        self.assertRaises(ArgumentError, Base_Executor(wf).run, mode='dryrun')
        #
        script = SoS_Script('''
parameter: b = list
[0]
''')
        self.assertEqual(list(wf.parameters().keys()), ['b'])
        wf = script.workflow()
        self.assertRaises(ArgumentError, Base_Executor(wf).run, mode='dryrun')
        # also require the type
        script = SoS_Script('''
parameter: b = int
[0]
''')
        wf = script.workflow()
        self.assertRaises(ArgumentError, Base_Executor(
            wf, args=['--b', 'file']).run, mode='dryrun')
        #
        script = SoS_Script('''
parameter: b = int
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--b', '5']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['b'], 5)
        env.sos_dict.pop('b')
        # string
        script = SoS_Script('''
parameter: b = str
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--b', '5']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['b'], '5')
        env.sos_dict.pop('b')
        # list is ok
        script = SoS_Script('''
parameter: b = list
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--b', '5']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['b'], ['5'])
        # bool required
        script = SoS_Script('''
# comment
parameter: b = bool
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--b']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['b'], True)
        env.sos_dict.pop('b')
        Base_Executor(wf, args=['--no-b']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['b'], False)
        env.sos_dict.pop('b')
        # bool with default True
        script = SoS_Script('''
parameter: b = True
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=[]).run(mode='dryrun')
        self.assertEqual(env.sos_dict['b'], True)
        env.sos_dict.pop('b')
        Base_Executor(wf, args=['--b']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['b'], True)
        env.sos_dict.pop('b')
        Base_Executor(wf, args=['--no-b']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['b'], False)
        env.sos_dict.pop('b')
        # bool with default False
        script = SoS_Script('''
parameter: b = False
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=[]).run(mode='dryrun')
        self.assertEqual(env.sos_dict['b'], False)
        env.sos_dict.pop('b')
        Base_Executor(wf, args=['--b']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['b'], True)
        env.sos_dict.pop('b')
        Base_Executor(wf, args=['--no-b']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['b'], False)
        env.sos_dict.pop('b')
        #
        # parameters cannot coincide with a readonly global variable
        # are masked by previous definition
        script = SoS_Script('''
a = 4
parameter: a = 5
[0]
''')
        wf = script.workflow()
        self.assertRaises(Exception, Base_Executor(
            wf, args=['--a', 7]).run, mode='dryrun')
        #self.assertEqual(env.sos_dict['a'], 4)
        #
        # test parameters with dash
        script = SoS_Script('''
parameter: a_b = 5
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--a_b', '10']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['a_b'], 10)
        env.sos_dict.pop('a_b')
        Base_Executor(wf, args=['--a-b', '10']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['a_b'], 10)
        env.sos_dict.pop('a_b')
        #
        #
        script = SoS_Script('''
parameter: a_b = int
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--a_b', '10']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['a_b'], 10)
        env.sos_dict.pop('a_b')
        Base_Executor(wf, args=['--a-b', '10']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['a_b'], 10)
        env.sos_dict.pop('a_b')
        #
        # test support for type path, paths, file_target and sos_targets
        script = SoS_Script('''
parameter: path_var = path
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--path-var', 'a.txt']).run(mode='run')
        self.assertTrue(isinstance(env.sos_dict['path_var'], path))
        #
        script = SoS_Script('''
parameter: path_var = file_target
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--path-var', 'a.txt']).run(mode='run')
        self.assertTrue(isinstance(env.sos_dict['path_var'], file_target))
        #
        script = SoS_Script('''
parameter: path_var = paths
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--path-var', 'a.txt', 'b.txt']).run(mode='run')
        self.assertTrue(isinstance(env.sos_dict['path_var'], paths))
        #
        #
        script = SoS_Script('''
parameter: path_var = sos_targets
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--path-var', 'a.txt']).run(mode='run')
        self.assertTrue(isinstance(env.sos_dict['path_var'], sos_targets))

        #
        script = SoS_Script('''
parameter: path_var = path('a.txt')
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--path-var', 'a.txt']).run(mode='run')
        self.assertTrue(isinstance(env.sos_dict['path_var'], path))
        #
        script = SoS_Script('''
parameter: path_var = file_target('a.txt')
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--path-var', 'a.txt']).run(mode='run')
        self.assertTrue(isinstance(env.sos_dict['path_var'], file_target))
        #
        script = SoS_Script('''
parameter: path_var = paths('a.txt')
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--path-var', 'a.txt', 'b.txt']).run(mode='run')
        self.assertTrue(isinstance(env.sos_dict['path_var'], paths))
        #
        #
        script = SoS_Script('''
parameter: path_var = sos_targets('a.txt')
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--path-var', 'a.txt']).run(mode='run')
        self.assertTrue(isinstance(env.sos_dict['path_var'], sos_targets))

        #
        # Test allow the use of sos keywords as parameters #1041
        script = SoS_Script('''\
[1]
parameter: input = 5
output = 10
python: expand=True
  print({input})
''')
        wf = script.workflow()
        Base_Executor(wf).run()
        # multiple parameters
        script = SoS_Script('''
parameter: a_b = int
[0]
parameter: c_b = list
''')
        wf = script.workflow()
        self.assertEqual(sorted(list(wf.parameters().keys())), ['a_b', 'c_b'])

#    this test is no longer valid because sos has stopped parsing assignments
#
#    def testSectionVariables(self):
#        '''Test variables in sections'''
#        # directive name cannot be used as variable
#        self.assertRaises(ParsingError, SoS_Script,
#            '''[0]
# input='a.txt' ''')
#        self.assertRaises(ParsingError, SoS_Script,
#            '''[0]
# output='a.txt' ''')
#        self.assertRaises(ParsingError, SoS_Script,
#            '''[0]
# depends='a.txt' ''')

    def testTypeTraitParameter(self):
        # type trait
        script = SoS_Script('''
parameter: b
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--b', '5']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['b'], '5')
        #
        script = SoS_Script('''
parameter: b :str
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--b', '5']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['b'], '5')
        #
        script = SoS_Script('''
parameter: b : list
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--b', '5']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['b'], ['5'])

        #
        script = SoS_Script('''
parameter: b : list = 5
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--b', '5']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['b'], 5)
        #
        script = SoS_Script('''
parameter: b : int
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--b', '5']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['b'], 5)

    def testInputTarget(self):
        # test input of targets
        script = SoS_Script('''
parameter: b : file_target
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--b', 'aaa']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['b'].__class__.__name__, 'file_target')
        #
        script = SoS_Script('''
parameter: b = file_target('file')
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--b', 'aaa']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['b'].__class__.__name__, 'file_target')
        #
        script = SoS_Script('''
parameter: b : sos_targets
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--b', 'aaa', 'bbb']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['b'].__class__.__name__, 'sos_targets')
        #
        script = SoS_Script('''
parameter: b = sos_targets('file')
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--b', 'aaa']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['b'].__class__.__name__, 'sos_targets')
        #
        script = SoS_Script('''
parameter: a_b : file_target
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--a-b', 'aaa']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['a_b'].__class__.__name__, 'file_target')
        #
        script = SoS_Script('''
parameter: a_b = file_target('file')
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--a-b', 'aaa']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['a_b'].__class__.__name__, 'file_target')
        #
        script = SoS_Script('''
parameter: a_b : sos_targets
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--a-b', 'aaa', 'bbb']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['a_b'].__class__.__name__, 'sos_targets')
        #
        script = SoS_Script('''
parameter: a_b = sos_targets('file')
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--a-b', 'aaa']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['a_b'].__class__.__name__, 'sos_targets')
        #
        #
        #
        #
        script = SoS_Script('''
parameter: b : path
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--b', 'aaa']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['b'].__class__.__name__, 'path')
        #
        script = SoS_Script('''
parameter: b = path('file')
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--b', 'aaa']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['b'].__class__.__name__, 'path')
        #
        script = SoS_Script('''
parameter: b : paths
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--b', 'aaa', 'bbb']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['b'].__class__.__name__, 'paths')
        #
        script = SoS_Script('''
parameter: b = paths('file')
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--b', 'aaa']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['b'].__class__.__name__, 'paths')
        #
        script = SoS_Script('''
parameter: a_b : path
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--a-b', 'aaa']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['a_b'].__class__.__name__, 'path')
        #
        script = SoS_Script('''
parameter: a_b = path('file')
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--a-b', 'aaa']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['a_b'].__class__.__name__, 'path')
        #
        script = SoS_Script('''
parameter: a_b : paths
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--a-b', 'aaa', 'bbb']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['a_b'].__class__.__name__, 'paths')
        #
        script = SoS_Script('''
parameter: a_b = paths('file')
[0]
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--a-b', 'aaa']).run(mode='dryrun')
        self.assertEqual(env.sos_dict['a_b'].__class__.__name__, 'paths')
        #

    def testSectionDirectives(self):
        '''Test directives of sections'''
        # cannot be in the global section
        # multi-line OK
        SoS_Script('''
[0]
input: 'filename',
    'filename1'

''')
        # An abusive case with multi-line OK, from first column ok, blank line ok
        SoS_Script('''
[0]
input: 'filename',
'filename1',

filename4,
opt1=value
output:
    blah

depends:
'something else'
''')
        # option with expression ok
        SoS_Script('''
[0]
input: 'filename',  'filename2', opt=value==1

''')
        # unrecognized directive, allowed now
        SoS_Script('''
[0]
something: 'filename',  filename2, opt=value==1
''')
        # need commma
        self.assertRaises(ParsingError, SoS_Script, '''
[0]
input: 'filename'  filename2
''')
        # can be after action
        SoS_Script('''
[0]
func()
input: 'filename',  'filename2', opt=value==1
''')
        # assignments between directives are allowed
        SoS_Script('''
[0]
input: 'filename',  'filename2', opt=value==1
a = 'some text'
output: 'filename',  'filename2', opt=value==1
''')
        # can have action between directives
        SoS_Script('''
[0]
input: 'filename',  'filename2', opt=value==1
abc
output: 'filename',  'filename2', opt=value==1
''')

    def testScriptFormat(self):
        '''Test putting scripts directly under action'''
        script = SoS_Script('''
[0]
input: 'filename',  'filename2', opt=value==1
R:

open('something')
save.put()

''')
        script = SoS_Script('''
[0]
input: 'filename',  'filename2', opt=value==1
R: concurrent = True

open('something')
save.put()

''')
        script = SoS_Script('''
[0]
input: 'filename',  'filename2', opt=value==1
R: concurrent = True,
    workdir = 'someelse else'

open('something')
save.put()

''')
        # test dedent
        script = SoS_Script('''
[0]
python3:
    from sos.runtime import logger
    logger.warning('I am from a dented text')
    if 1:
        logger.warning('Another warning')
''')
        script.workflow()
        # with section head in the script,
        # this will not work even if the embedded
        # python script is perfectly valid.
        self.assertRaises(ParsingError, SoS_Script, '''
[0]
input: 'filename',  'filename2', opt=value==1
python3:

with open('something') as e:
   e.write("""
[section]
""")

''')
        # scripts with section head-like lines
        script = SoS_Script('''
[0]
R:
some::function(param)
''')
        script.workflow()
        #
        # script with first-line indent
        #
        script = SoS_Script('''
[0]
sh:
  echo "a"

sh('echo "b"')
''')
        script.workflow()

    def testInput(self):
        '''Test input directive'''
        self.touch(['a.txt', 'b.txt', 'a.pdf', 'a0', 'a1'])
        script = SoS_Script('''
[0]
files = ['a.txt', 'b.txt']

input: 'a.pdf', files

''')
        wf = script.workflow()
        Base_Executor(wf).run(mode='dryrun')
        #
        # test input types
        script = SoS_Script('''
[0:shared={'i':'_input', 'o':'_output'}]
files = (f"a{i}" for i in range(2))
input: {'a.txt', 'b.txt'}, files
output: (f"a{x}" for x in _input)

''')
        wf = script.workflow()
        Base_Executor(wf).run(mode='dryrun')
        self.assertEqual(sorted(env.sos_dict['i']), sos_targets(
            ['a.txt', 'a0', 'a1', 'b.txt']))
        self.assertEqual(sorted(env.sos_dict['o']), sos_targets([
                         'aa.txt', 'aa0', 'aa1', 'ab.txt']))

    def testGroupBy(self):
        '''Test group_by parameter of step input'''
        # group_by = 'all'
        self.touch(['a{}.txt'.format(x) for x in range(15)])
        #
        script = SoS_Script('''
[0: shared='executed']

executed = []
input: [f'a{x}.txt' for x in range(1, 5)], group_by='all'

executed.append(_input)

''')
        wf = script.workflow()
        Base_Executor(wf).run(mode='dryrun')
        self.assertEqual(env.sos_dict['executed'],  [
                         sos_targets('a1.txt', 'a2.txt', 'a3.txt', 'a4.txt')])
        self.assertEqual(env.sos_dict['executed'][0].labels, ['0']*4)
        # group_by = 'single'
        script = SoS_Script('''
[0: shared='executed']

executed = []
input: ['a{}.txt'.format(x) for x in range(1, 5)], group_by='single'

executed.append(_input)

''')
        wf = script.workflow()
        Base_Executor(wf).run(mode='dryrun')
        self.assertEqual(env.sos_dict['executed'],  [sos_targets('a1.txt'), sos_targets(
            'a2.txt'), sos_targets('a3.txt'), sos_targets('a4.txt')])
        # group_by = 'pairs'
        script = SoS_Script('''
[0: shared='executed']

executed = []
input: [f'a{x}.txt' for x in range(1, 5)], group_by='pairs'

executed.append(_input)

''')
        wf = script.workflow()
        Base_Executor(wf).run(mode='dryrun')
        self.assertEqual(env.sos_dict['executed'],  [sos_targets(
            'a1.txt', 'a3.txt'), sos_targets('a2.txt', 'a4.txt')])
        # group_by = 'pairs2'
        script = SoS_Script('''
[0: shared='executed']

executed = []
input: [f'a{x}.txt' for x in range(1, 9)], group_by='pairs2'

executed.append(_input)

''')
        wf = script.workflow()
        Base_Executor(wf).run(mode='dryrun')
        self.assertEqual(env.sos_dict['executed'],  [
                sos_targets('a1.txt', 'a2.txt', 'a5.txt', 'a6.txt'),
                sos_targets('a3.txt', 'a4.txt', 'a7.txt', 'a8.txt')
                ])
        # group_by = 'pairs3'
        script = SoS_Script('''
[0: shared='executed']

executed = []
input: [f'a{x}.txt' for x in range(1, 13)], group_by='pairs3'

executed.append(_input)

''')
        wf = script.workflow()
        Base_Executor(wf).run(mode='dryrun')
        self.assertEqual(env.sos_dict['executed'],  [
                sos_targets('a1.txt', 'a2.txt', 'a3.txt', 'a7.txt', 'a8.txt', 'a9.txt'),
                sos_targets('a4.txt', 'a5.txt', 'a6.txt', 'a10.txt', 'a11.txt', 'a12.txt')
                ])

        # group_by = 'pairwise'
        script = SoS_Script('''
[0: shared='executed']

executed = []
input: ['a{}.txt'.format(x) for x in range(1, 5)], group_by='pairwise'

executed.append(_input)

''')
        wf = script.workflow()
        Base_Executor(wf).run(mode='dryrun')
        self.assertEqual(env.sos_dict['executed'],  [sos_targets('a1.txt', 'a2.txt'), sos_targets(
            'a2.txt', 'a3.txt'), sos_targets('a3.txt', 'a4.txt')])
        # group_by = 'pairwiseN'
        script = SoS_Script('''
[0: shared='executed']

executed = []
input: ['a{}.txt'.format(x) for x in range(1, 7)], group_by='pairwise2'

executed.append(_input)

''')
        wf = script.workflow()
        Base_Executor(wf).run(mode='dryrun')
        self.assertEqual(env.sos_dict['executed'],  [
            sos_targets('a1.txt', 'a2.txt', 'a3.txt', 'a4.txt'),
            sos_targets('a3.txt', 'a4.txt', 'a5.txt', 'a6.txt')
            ],
            f'obtained {env.sos_dict["executed"]}')

        # group_by = 'combinations'
        script = SoS_Script('''
[0: shared='executed']

executed = []
input: ['a{}.txt'.format(x) for x in range(1, 5)], group_by='combinations'

executed.append(_input)

''')
        wf = script.workflow()
        Base_Executor(wf).run(mode='dryrun')
        self.assertEqual(env.sos_dict['executed'],  [sos_targets('a1.txt', 'a2.txt'), sos_targets('a1.txt', 'a3.txt'),
                                                     sos_targets('a1.txt', 'a4.txt'), sos_targets('a2.txt', 'a3.txt'), sos_targets('a2.txt', 'a4.txt'), sos_targets('a3.txt', 'a4.txt')])

        # group_by = 'combinations3'
        script = SoS_Script('''
[0: shared='executed']

executed = []
input: ['a{}.txt'.format(x) for x in range(1, 5)], group_by='combinations3'

executed.append(_input)

''')
        wf = script.workflow()
        Base_Executor(wf).run(mode='dryrun')
        self.assertEqual(env.sos_dict['executed'],
            [
            sos_targets(['a1.txt', 'a2.txt', 'a3.txt']),
            sos_targets(['a1.txt', 'a2.txt', 'a4.txt']),
            sos_targets(['a1.txt', 'a3.txt', 'a4.txt']),
            sos_targets(['a2.txt', 'a3.txt', 'a4.txt'])
            ], f'obtained {env.sos_dict["executed"]}')
        # group_by chunks specified as integers
        script = SoS_Script('''
[0: shared='executed']

executed = []
input: ['a{}.txt'.format(x) for x in range(1, 10)], group_by=3

executed.append(_input)

''')
        wf = script.workflow()
        Base_Executor(wf).run(mode='dryrun')
        self.assertEqual(env.sos_dict['executed'], [
            sos_targets('a1.txt', 'a2.txt', 'a3.txt'),
            sos_targets('a4.txt', 'a5.txt', 'a6.txt'),
            sos_targets('a7.txt', 'a8.txt', 'a9.txt')])
        # group_by chunks specified as integer strings
        script = SoS_Script('''
[0: shared='executed']

executed = []
input: ['a{}.txt'.format(x) for x in range(1, 10)], group_by='3'

executed.append(_input)

''')
        wf = script.workflow()
        Base_Executor(wf).run(mode='dryrun')
        self.assertEqual(env.sos_dict['executed'], [
                         sos_targets('a1.txt', 'a2.txt', 'a3.txt'),
                         sos_targets('a4.txt', 'a5.txt', 'a6.txt'),
                         sos_targets('a7.txt', 'a8.txt', 'a9.txt')])
        # number of files should be divisible by group_by
        self.touch(['a{}.txt'.format(x) for x in range(1, 10)])
        script = SoS_Script('''
[0]

executed = []
input: ['a{}.txt'.format(x) for x in range(1, 10)], group_by=4

executed.append(_input)

''')
        wf = script.workflow()
        Base_Executor(wf).run(mode="dryrun")
        # incorrect value causes an exception
        script = SoS_Script('''
[0]

executed = []
input: ['a{}.txt'.format(x) for x in range(1, 10)], group_by='something'

executed.append(_input)

''')
        wf = script.workflow()
        self.assertRaises(Exception, Base_Executor(wf).run, mode="dryrun")
        #
        # group by source
        file_target('c.txt').touch()
        script = SoS_Script('''
[A]
output: 'a.txt'
_output.touch()

[B]
input: for_each={'i': range(2)}
output: 'b.txt', 'b1.txt', group_by=1
_output.touch()

[0: shared='executed']
executed = []

input: 'c.txt', output_from(['A', 'B']), group_by='source'

executed.append(_input)

''')
        wf = script.workflow()
        Base_Executor(wf).run(mode='dryrun')
        self.assertEqual(env.sos_dict['executed'], [
                         sos_targets('c.txt'),
                         sos_targets('a.txt'),
                         sos_targets('b.txt', 'b1.txt')])
        #
        # group_by='pairsource'
        file_target('c.txt').touch()
        script = SoS_Script('''
[A]
output: 'a1.txt', 'a2.txt'
_output.touch()

[B]
output: 'b1.txt', 'b2.txt'
_output.touch()

[0: shared='executed']
executed = []

input: output_from(['A', 'B']), group_by='pairsource'

executed.append(_input)

''')
        wf = script.workflow()
        Base_Executor(wf).run(mode='dryrun')
        self.assertEqual(env.sos_dict['executed'], [
                         sos_targets('a1.txt', 'b1.txt'),
                         sos_targets('a2.txt', 'b2.txt')])
        # group_by='pairsource3'
        self.touch(['c{}.txt'.format(x) for x in range(1, 7)])

        script = SoS_Script('''
[A]
output: [f'a{x}.txt' for x in range(1, 7)]
_output.touch()

[B]
output: [f'b{x}.txt' for x in range(1, 7)]
_output.touch()

[0: shared='executed']
executed = []

input: [f'c{x}.txt' for x in range(1, 7)], output_from(['A', 'B']), group_by='pairsource3'

executed.append(_input)

''')
        wf = script.workflow()
        Base_Executor(wf).run(mode='dryrun')
        self.assertEqual(env.sos_dict['executed'], [
                         sos_targets('c1.txt', 'c2.txt', 'c3.txt', 'a1.txt', 'a2.txt', 'a3.txt', 'b1.txt', 'b2.txt', 'b3.txt'),
                         sos_targets('c4.txt', 'c5.txt', 'c6.txt', 'a4.txt', 'a5.txt', 'a6.txt', 'b4.txt', 'b5.txt', 'b6.txt')])
        # group_by='pairsource3'
        self.touch(['c{}.txt'.format(x) for x in range(1, 7)])

        script = SoS_Script('''
[A]
output: 'a1.txt'
_output.touch()

[B]
output: [f'b{x}.txt' for x in range(1, 7)]
_output.touch()

[0: shared='executed']
executed = []

input: [f'c{x}.txt' for x in range(1, 3)], output_from(['A', 'B']), group_by='pairsource3'

executed.append(_input)

''')
        wf = script.workflow()
        Base_Executor(wf).run(mode='dryrun')
        self.assertEqual(env.sos_dict['executed'], [
                         sos_targets('c1.txt', 'a1.txt', 'b1.txt', 'b2.txt', 'b3.txt'),
                         sos_targets('c2.txt', 'a1.txt', 'b4.txt', 'b5.txt', 'b6.txt')])
        #
        # group by function
        file_target('c.txt').touch()
        script = SoS_Script('''
[0: shared='executed']
executed = []

def grp(x):
    return  [x[:3], x[3:]]

input: ['a{}.txt'.format(x) for x in range(5)], group_by=grp

executed.append(_input)

''')
        wf = script.workflow()
        Base_Executor(wf).run(mode='dryrun')
        self.assertEqual(env.sos_dict['executed'], [
                         ['a0.txt', 'a1.txt', 'a2.txt'],
                         ['a3.txt', 'a4.txt']])
        #
        # group by lambda function
        file_target('c.txt').touch()
        script = SoS_Script('''
[0: shared='executed']
executed = []

input: ['a{}.txt'.format(x) for x in range(6)], group_by=lambda x: zip(x[:3], x[3:])

executed.append(_input)

''')
        wf = script.workflow()
        Base_Executor(wf).run(mode='dryrun')
        self.assertEqual(env.sos_dict['executed'], [
                         ['a0.txt', 'a3.txt'],
                         ['a1.txt', 'a4.txt'],
                         ['a2.txt', 'a5.txt']])


    def testOutputGroupBy(self):
        '''Test group_by parameter of step output'''
        # group_by = 'all'
        self.touch(['a{}.txt'.format(x) for x in range(4)])
        #
        script = SoS_Script('''
[0: shared='executed']

executed = []
input: ['a{}.txt'.format(x) for x in range(4)], group_by=2
output: ['a{}.txt.bak'.format(x) for x in range(4)], group_by=2

executed.append(_output)

''')
        wf = script.workflow()
        Base_Executor(wf).run(mode='dryrun')
        self.assertEqual(env.sos_dict['executed'], [sos_targets(
            'a0.txt.bak', 'a1.txt.bak'), sos_targets('a2.txt.bak', 'a3.txt.bak')])

    def testStepsWithStepName(self):
        '''Test from steps'''
        script = SoS_Script('''
[step_10]

output: 'a.txt'
_output.touch()

[step_20]
input: output_from(step_name.split('_')[0] + '_10')
print(_input)
''')
        wf = script.workflow()
        Base_Executor(wf).run()
        #
        script = SoS_Script('''
[step_10]

output: 'a.txt'
_output.touch()

[step_20]
input: output_from(10)
print(_input)
''')
        wf = script.workflow()
        Base_Executor(wf).run()        

    def testSectionActions(self):
        '''Test actions of sections'''
        SoS_Script(
            """
[0]
func('''
multiline
string''', with_option=1
)
""")
        self.assertRaises(ParsingError, SoS_Script,
                          '''
[0]
func(
''')

    def testLongerCode(self):
        '''Test definition of classes (with intermediate newlines) in step.'''
        script = SoS_Script('''# first block

[0: shared='b']
class A:
    def __init__(self):
        pass

    # the newline above should be fine because SoS treat this as
    # regular lines
    def __call__(self):
        return 0

b = A()()

''')
        wf = script.workflow()
        Base_Executor(wf).run()
        self.assertEqual(env.sos_dict['b'], 0)

    def testCombinedWorkflow(self):
        '''Test the creation and execution of combined workfow'''
        script = SoS_Script('''
a0 = 0
if 'executed' not in locals():
    executed = []
parameter: a = a0 + 1
[a_1: shared='executed']
executed.append(step_name)
[a_2: shared='executed']
executed.append(step_name)
[a_3: shared='executed']
executed.append(step_name)
[a_4: shared='executed']
executed.append(step_name)
output: 'out_a_4'
[b_1: shared=['executed', 'input_b1']]
executed.append(step_name)
input_b1 = _input
[b_2: shared='executed']
executed.append(step_name)
[b_3: shared='executed']
executed.append(step_name)
[b_4: shared='executed']
executed.append(step_name)
[c: shared='executed']
executed.append(step_name)
[d: shared='executed']
executed.append(step_name)
''')
        wf = script.workflow('a+b')
        Base_Executor(wf).run(mode='dryrun')
        self.assertEqual(env.sos_dict['executed'], ['a_1', 'a_2',
                                                    'a_3', 'a_4', 'b_1', 'b_2', 'b_3', 'b_4'])
        self.assertEqual(env.sos_dict['a'], 1)
        self.assertEqual(env.sos_dict['input_b1'], ['out_a_4'])
        #
        env.sos_dict.pop('executed', None)
        wf = script.workflow('a: 1-2 + a:4 + b:3-')
        Base_Executor(wf).run(mode='dryrun')
        self.assertEqual(env.sos_dict['executed'], ['a_1', 'a_2', 'a_4',
                                                    'b_3', 'b_4'])
        #
        env.sos_dict.pop('executed', None)
        wf = script.workflow('a+c+d')
        Base_Executor(wf).run(mode='dryrun')
        self.assertEqual(env.sos_dict['executed'], [
                         'a_1', 'a_2', 'a_3', 'a_4', 'c', 'd'])

    def testIncludeWithNamespace(self):
        '''Test include a workflow that uses variables from its own global module'''
        self.touch(['a.txt', 'b.txt'])
        #
        with open('inc.sos', 'w') as sos:
            sos.write('''
# test sos script

# global definition
parameter: parB = 10

[A_1]
a = parB + 1

''')
        script = SoS_Script('''
%include inc

''')
        wf = script.workflow('inc.A')
        Base_Executor(wf).run(mode='dryrun')

    def testYAMLConfig(self):
        '''Test config file in yaml format'''
        with open('myconfig.yml', 'w') as config:
            config.write('''
# Lines beginning with # are skipped when the JSON is parsed, so we can
# put comments into our JSON configuration files
{
    StoreOwner : "John Doe",

    # List of items that we sell
    Fruits: [ "apple", "banana", "pear" ],
    Price: 1.05
}
''')
        with open('config.sos', 'w') as sos:
            sos.write('''
[0]
print(CONFIG['StoreOwner'])
print(CONFIG.get('StoreOwner', 'something'))
print(CONFIG.get('StoreOwnerSpouse', 'someone else'))
#print(CONFIG.StoreOwner)
'''
                      )
        # run the command
        self.assertEqual(subprocess.call('sos run config.sos -c myconfig.yml',
                                         stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, shell=True), 0)
        # now test the value
        script = SoS_Script(filename='config.sos')
        wf = script.workflow()
        Base_Executor(wf, config={'config_file': 'myconfig.yml'}).run()
        self.assertEqual(env.sos_dict['CONFIG']['Price'], 1.05)
        self.assertEqual(env.sos_dict['CONFIG']['StoreOwner'], 'John Doe')
        self.assertEqual(env.sos_dict['CONFIG']['Fruits'], [
                         'apple', 'banana', 'pear'])

    def testVarOutput(self):
        '''Test early appearance of variable output'''
        script = SoS_Script('''
[0]
seq = range(3)
input: for_each='seq'
output: f"test{_seq}.txt"
print(_output)
''')
        wf = script.workflow()
        # this does not work before until we make variable output available sooner
        Base_Executor(wf).run(mode='dryrun')

    def testInclude(self):
        '''Test include keyword'''
        with open('inc.sos', 'w') as ts:
            ts.write('''
# a slave script to be included
gv = 1
[A_1]
[A_2]
[B]
''')
        script = SoS_Script('''
%include inc
res = inc.gv
[0]
''')
        wf = script.workflow()
        Base_Executor(wf).run(mode='dryrun')
        Base_Executor(wf).run()
        self.assertEqual(env.sos_dict['res'], 1)
        #
        # include with alias
        script = SoS_Script('''
%include inc as tt
res1 = tt.gv
[0]
''')
        wf = script.workflow()
        Base_Executor(wf).run(mode='dryrun')
        Base_Executor(wf).run()
        self.assertEqual(env.sos_dict['res1'], 1)
        os.remove('inc.sos')

    def testFromInclude(self):
        '''Test include keyword'''
        with open('inc.sos', 'w') as ts:
            ts.write('''
# a slave script to be included
gv = 1
[A_1]
[A_2]
[B]
''')
        script = SoS_Script('''
%from inc include gv
[0]
''')
        wf = script.workflow()
        Base_Executor(wf).run(mode='dryrun')
        Base_Executor(wf).run()
        self.assertEqual(env.sos_dict['gv'], 1)
        #
        # include with alias
        script = SoS_Script('''
%from inc include gv as g
res1 = g
[0]
''')
        wf = script.workflow()
        Base_Executor(wf).run(mode='dryrun')
        Base_Executor(wf).run()
        self.assertEqual(env.sos_dict['res1'], 1)

    def testCell(self):
        '''Test ignoring %cell'''
        SoS_Script('''
%cell 1
[step ]
a = 1
''')

    def testIfElse(self):
        '''Test if/elif/else/endif structural directive'''
        # no matching %endif
        self.assertRaises(ParsingError, SoS_Script, '''
%if 1
a = 1
%else
a=2
''')
        # no if for else
        self.assertRaises(ParsingError, SoS_Script, '''
%else
a=2
''')
        # no conditon for if
        self.assertRaises(ParsingError, SoS_Script, '''
%if
a=2
%endif
''')
        # no conditon for elif
        self.assertRaises(ParsingError, SoS_Script, '''
%if 1
%elif
a=2
%endif
[0]
''')
        # test if else
        script = SoS_Script('''
%if 0
a = 1
%else
a = 2
%endif
[0]
''')
        wf = script.workflow()
        Base_Executor(wf).run(mode='dryrun')
        self.assertEqual(env.sos_dict['a'], 2)

    def testOverwriteKeyword(self):
        '''Test overwrite sos keyword with user defined one.'''
        if file_target('a.txt').exists():
            file_target('a.txt').unlink()
        #
        script = SoS_Script('''
def run(script):
    pass

[1]
run:
    touch a.txt
''')
        wf = script.workflow()
        Base_Executor(wf).run()
        self.assertFalse(os.path.isfile('a.txt'))
        #
        script = SoS_Script('''
parameter: run = 5

[1]
run:
    touch a.txt
''')
        wf = script.workflow()
        self.assertRaises(Exception, Base_Executor(wf).run)

    def testComments(self):
        '''Test the use of comments in sos script'''
        # extract workflow from ipynb
        wf = extract_workflow('sample_workflow.ipynb')
        self.assertFalse('this is a test workflow' in wf)
        self.assertEqual(
            wf.count('this comment will be included but not shown in help'), 1)
        self.assertTrue(
            wf.count('this comment will become the comment for parameter b'), 1)
        self.assertTrue(
            wf.count('this comment will become the comment for parameter d'), 1)
        self.assertFalse('this is a cell with another kernel' in wf)
        self.assertFalse(
            'this comment will not be included in exported workflow' in wf)

    def testHelpMessage(self):
        '''Test help message from ipynb notebook'''
        msg = subprocess.check_output(
            'sos run sample_workflow.ipynb -h', shell=True).decode()
        self.assertFalse(
            'this comment will be included but not shown in help' in msg)
        self.assertTrue(
            msg.count('this comment will become the comment for parameter b'), 1)
        self.assertTrue(
            msg.count('this comment will become the comment for parameter d'), 1)
        self.assertTrue(msg.count('--c 3 (as int)'), 1)
        self.assertTrue(
            msg.count('this is a section comment, will be displayed'), 1)
        self.assertFalse('this is a test workflow' in msg)
        self.assertFalse('this is a cell with another kernel' in msg)
        self.assertFalse(
            'this comment will not be included in exported workflow' in msg)

    def testHelpOnMultiWorkflow(self):
        '''Test help message of sos file (#985)'''
        with open('test_msg.sos', 'w') as script:
            script.write('''\
[workflow_a_10,workflow_b]
[workflow_a_20]
[default]
''')
        msg = subprocess.check_output(
            'sos run test_msg.sos -h', shell=True).decode()
        self.assertTrue('workflow_a' in msg)
        self.assertTrue('workflow_b' in msg)
        # when introducing sections
        self.assertTrue('workflow_a_10, workflow_b' in msg)
        self.assertTrue('default' in msg)

    def testParameterAbbreviation(self):
        '''Test potential problem caused by parameter abbreviation #1053'''
        if os.path.isfile('0914.txt'):
            os.remove('0914.txt')
        script = SoS_Script('''
[global]
parameter: name = '0914'

[1]
parameter: n = 4
output: f'{name}.txt'
print(_output)
_output.touch()
''')
        wf = script.workflow()
        Base_Executor(wf, args=['--n', '5']).run()
        self.assertTrue(os.path.isfile('0914.txt'))

    def testNamedInput(self):
        '''Test named input'''
        for filename in ('a.txt', 'b.txt'):
            with open(filename, 'w') as out:
                out.write(filename + '\n')
        script = SoS_Script('''
[1]
input: {'A': 'a.txt', 'B': 'b.txt'}, group_by='pairsource'
output: 'c.txt'
assert _input['A'] == [file_target('a.txt')]
assert _input['B'] == [file_target('b.txt')]
with open(_output, 'w') as out:
    out.write(open(_input['A']).read())
    out.write(open(_input['B']).read())
''')
        wf = script.workflow()
        Base_Executor(wf).run()
        self.assertTrue(open('c.txt').read(), 'a.txt\nb.txt\n')


if __name__ == '__main__':
    #suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestParser)
    # unittest.TextTestRunner(, suite).run()
    unittest.main()
