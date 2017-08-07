#!/usr/bin/env python
__author__ = "Gao Wang"
__copyright__ = "Copyright 2016, Stephens lab"
__email__ = "gaow@uchicago.edu"
__license__ = "MIT"
'''
This file defines methods to translate DSC into pipeline in SoS language
'''
import re, os, datetime, msgpack, glob
from sos.target import fileMD5, textMD5, executable
from .utils import OrderedDict, flatten_list, uniq_list, dict2str, convert_null, n2a

class DSC_Translator:
    '''
    Translate workflow to SoS pipeline:
      * Each DSC computational routine `exec` is a sos step with name `group + command index`
      * When there are combined routines in a block via `.logic` for `exec` then sub-steps are generated
        with name `group + super command index + command index` without alias name then
        create nested workflow named `group + combined routine index`
      * FIXME: to above, because it still produce intermediate files which is not what we want
      * Parameters utilize `for_each`. `paired_with` is not supported
      * Final workflow also use nested workflow structure,
        with workflow name "DSC" for each sequence, indexed by
        the possible ways to combine exec routines. The possible ways are pre-determined and passed here.
    '''
    def __init__(self, workflows, runtime, rerun = False, n_cpu = 4, try_catch = False):
        #
        from .plugin import R_LMERGE, R_SOURCE
        self.output = runtime.output
        self.db = os.path.basename(runtime.output)
        conf_header = 'import msgpack\nfrom collections import OrderedDict\n' \
                      'from dsc.utils import sos_hash_output, sos_group_input, chunks\n' \
                      'from dsc.dsc_database import remove_obsolete_output, build_config_db\n\n\n'
        job_header = "import msgpack\nfrom collections import OrderedDict\n"\
                     "parameter: IO_DB = msgpack.unpackb(open('{}/{}.conf.mpk'"\
                     ", 'rb').read(), encoding = 'utf-8', object_pairs_hook = OrderedDict)\n\n".\
                     format(self.output, self.db)
        processed_steps = []
        conf_dict = {}
        conf_str = []
        job_str = []
        exe_signatures = {}
        # name map for steps
        self.step_map = {}
        # Execution steps, unfiltered
        self.job_pool = OrderedDict()
        # Get workflow steps
        for workflow_id, workflow in enumerate(workflows):
            self.step_map[workflow_id] = {}
            keys = list(workflow.keys())
            for block in workflow.values():
                for step in block.steps:
                    name = "_".join([step.group, str(step.exe_id), '_'.join(keys[:keys.index(step.group)])])
                    if name not in processed_steps:
                        processed_steps.append(name)
                        pattern = re.compile("^{0}_{1}[0-9]+$".\
                                             format(step.group, n2a(step.exe_id)))
                        cnt = len([k for k in
                                   set(flatten_list([list(self.step_map[i].values()) for i in range(workflow_id)]))
                                   if pattern.match(k)])
                        name2 = "{}_{}{}".format(step.group, n2a(step.exe_id), cnt)
                        self.step_map[workflow_id]["{}_{}".format(step.group, step.exe_id)] = name2
                        step.exe_id = n2a(step.exe_id)
                        if cnt == 0:
                            job_translator = self.Step_Translator(step, self.db, 0, try_catch)
                            job_str.append(job_translator.dump())
                            job_translator.clean()
                        step.exe_id = "{}{}".format(step.exe_id, cnt)
                        conf_translator = self.Step_Translator(step, self.db, 1, try_catch)
                        conf_dict[name2] = conf_translator.dump()
                        exe_signatures[name2] = job_translator.exe_signature
        # Get workflows executions
        i = 1
        io_info_files = []
        final_step_label = []
        final_workflow_label = []
        for workflow_id, sequence in enumerate(runtime.sequence):
            sequence, step_ids = sequence
            for step_id in step_ids:
                sqn = ['{}_{}0'.format(x, n2a(y + 1))
                       if '{}_{}'.format(x, y + 1) not in self.step_map[workflow_id]
                       else self.step_map[workflow_id]['{}_{}'.format(x, y + 1)]
                       for x, y in zip(sequence, step_id)]
                # Configuration
                conf_str.append("[{0}]\n" \
                                "parameter: sequence_id = '{1}'\nparameter: sequence_name = '{2}'\n" \
                                "input: None\noutput: '{3}'".\
                                format(n2a(i), i, '+'.join(sqn), '.sos/.dsc/{1}_{0}.mpk'.format(i, self.db)))
                conf_str.append("DSC_UPDATES_ = OrderedDict()\n")
                conf_str.extend([conf_dict[x] for x in sqn])
                conf_str.append("open(output[0], 'wb').write(msgpack.packb(DSC_UPDATES_))")
                io_info_files.append('.sos/.dsc/{1}_{0}.mpk'.format(i, self.db))
                # Execution pool
                ii = 1
                for x in sqn:
                    y = re.sub(r'\d+$', '', x)
                    if ii == len(sqn):
                        final_workflow_label.append("{0}_{1}".format(y, n2a(i)))
                    tmp_str = ["[{0}_{1} ({0}[{2}])]".format(y, n2a(i), i)]
                    tmp_str.append("parameter: script_signature = {}".format(repr(exe_signatures[x])))
                    if ii > 1:
                        tmp_str.append("depends: [sos_step(x) for x in IO_DB['{1}']['{0}']['depends']]".\
                                       format(x, i))
                    tmp_str.append("output: IO_DB['{1}']['{0}']['output']".format(x, i))
                    tmp_str.append("sos_run('core_{0}', output_files = IO_DB['{2}']['{1}']['output']"\
                                   ", input_files = IO_DB['{2}']['{1}']['input'], "\
                                   "DSC_STEP_ID_ = script_signature)".format(y, x, i))
                    self.job_pool[(str(i), x)] = '\n'.join(tmp_str)
                    ii += 1
                final_step_label.append((str(i), x))
                i += 1
        self.conf_str = conf_header + '\n'.join(conf_str)
        self.job_str = job_header + "DSC_RUTILS = '''{}'''\n".format(R_SOURCE + R_LMERGE) + '\n'.join(job_str)
        self.conf_str += "\n[default_1]\nremove_obsolete_output('{0}', rerun = {2})\n[default_2]\n" \
                         "parameter: vanilla = {2}\ndepends: {4}\n" \
                         "input: dynamic({3})\noutput: '{0}/{1}.io.mpk', '{0}/{1}.map.mpk', '{0}/{1}.conf.mpk'"\
                         "\nbuild_config_db(input, output[0], output[1], "\
                         "output[2], vanilla = vanilla, jobs = {5})".\
                         format(self.output, self.db, rerun, repr(sorted(set(io_info_files))),
                                ", ".join(["sos_step('{}')".format(n2a(x+1)) for x, y in enumerate(set(io_info_files))]),
                                n_cpu)
        self.job_str += "\n[DSC]\ndepends: {}\noutput: sum([IO_DB[x[0]][x[1]]['output'] for x in {}], [])".\
                        format(', '.join(["sos_step('{}')".format(x) for x in final_workflow_label]),
                               repr(final_step_label))
        #
        self.install_libs(runtime.rlib, "R_library", rerun)
        self.install_libs(runtime.pymodule, "Python_Module", rerun)

    def write_pipeline(self, pipeline_id, dest = None):
        import tempfile
        res = []
        if pipeline_id == 1:
            res.extend(['## {}'.format(x) for x in dict2str(self.step_map).split('\n')])
            res.append(self.conf_str)
        else:
            res.append(self.job_str)
        output = dest if dest is not None else (tempfile.NamedTemporaryFile().name + '.sos')
        for item in glob.glob(os.path.join(os.path.dirname(output), "*.sos")):
            os.remove(item)
        with open(output, 'w') as f:
            f.write('\n'.join(res))
        return output

    def filter_execution(self):
        '''Filter steps removing the ones having common input and output'''
        IO_DB = msgpack.unpackb(open('{}/{}.conf.mpk'.format(self.output, self.db), 'rb').\
                                read(), encoding = 'utf-8', object_pairs_hook = OrderedDict)
        for x in self.job_pool:
            if x[0] in IO_DB and x[1] in IO_DB[x[0]]:
                self.job_str += '\n{}'.format(self.job_pool[x])

    @staticmethod
    def install_libs(libs, lib_type, force = False):
        from .utils import install_r_libs, install_py_modules
        if lib_type not in ["R_library", "Python_Module"]:
            raise ValueError("Invalid library type ``{}``.".format(lib_type))
        if libs is None:
            return
        libs_md5 = textMD5(repr(libs) + str(datetime.date.today()))
        if os.path.exists('.sos/.dsc/{}.{}.info'.format(lib_type, libs_md5)) and not force:
            return
        if lib_type == 'R_library':
            install_r_libs(libs)
        if lib_type == 'Python_Module':
            install_py_modules(libs)
        # FIXME: need to check if installation is successful
        os.makedirs('.sos/.dsc', exist_ok = True)
        with open('.sos/.dsc/{}.{}.info'.format(lib_type, libs_md5), 'w') as f:
            f.write(repr(libs))

    class Step_Translator:
        def __init__(self, step, db, prepare, try_catch):
            '''
            prepare step:
             - will produce source to build config and database for
            parameters and file names. The result is one binary json file (via msgpack)
            with keys "X:Y:Z" where X = DSC sequence ID, Y = DSC subsequence ID, Z = DSC step name
                (name of indexed DSC block corresponding to a computational routine).
            run step:
             - will construct the actual script to run
            '''
            # FIXME
            if len(flatten_list(list(step.rf.values()))) > 1:
                raise ValueError('Multiple output files not implemented')
            self.try_catch = try_catch
            self.exe_signature = []
            self.prepare = prepare
            self.step = step
            self.db = db
            self.input_vars = None
            self.header = ''
            self.loop_string = ''
            self.filter_string = ''
            self.param_string = ''
            self.input_string = ''
            self.output_string = ''
            self.input_option = []
            self.step_option = ''
            self.action = ''
            self.name = '{}_{}'.format(self.step.group, self.step.exe_id)
            self.get_header()
            self.get_parameters()
            self.get_input()
            self.get_output()
            self.get_step_option()
            self.get_action()

        def clean(self):
            for item in glob.glob('.sos/core_{0}*'.format(self.name)):
                os.remove(item)

        def get_header(self):
            if self.prepare:
                self.header = "## Codes for {1} ({0})".format(self.step.group, self.name)
            else:
                self.header = "[core_{0} ({1})]\n".\
                               format(self.name, self.step.name)
                self.header += "parameter: DSC_STEP_ID_ = None\nparameter: output_files = list"
                # FIXME: using [step.exe] for now as super step has not yet been ported over

        def get_parameters(self):
            # Set params, make sure each time the ordering is the same
            self.params = list(self.step.p.keys())
            for key in self.params:
                self.param_string += '{}{} = {}\n'.\
                                     format('' if self.prepare else "parameter: ", key,
                                            repr([convert_null(x, self.step.plugin.name) for x in self.step.p[key]]))
            if self.step.seed:
                self.params.append('seed')
                self.param_string += '{}seed = {}'.format('' if self.prepare else "parameter: ", repr(self.step.seed))
            if self.params:
                self.loop_string = ' '.join(['for _{0} in {0}'.format(s) for s in reversed(self.params)])
            if self.step.l:
                self.filter_string = ' if ' + self.step.l

        def get_input(self):
            depend_steps = uniq_list([x[0] for x in self.step.depends]) if self.step.depends else []
            if self.prepare:
                if depend_steps:
                    self.input_string += "## With variables from: {}".format(', '.join(depend_steps))
                if len(depend_steps) >= 2:
                    self.input_vars = 'input_files'
                    self.input_string += '\ninput_files = sos_group_input([{}])'.\
                       format(', '.join(['{}_output'.format(x) for x in depend_steps]))
                elif len(depend_steps) == 1:
                    self.input_vars = "{}_output".format(depend_steps[0])
                else:
                    pass
                if len(depend_steps):
                    self.loop_string += ' for __i in chunks({}, {})'.format(self.input_vars, len(depend_steps))
            else:
                if len(depend_steps):
                    self.input_string += "parameter: input_files = list\ninput: dynamic(input_files)"
                    self.input_option.append('group_by = {}'.format(len(depend_steps)))
                else:
                    self.input_string += "input:"
                if len(self.params):
                    if self.filter_string:
                        self.input_option.append("for_each = {{'{0}':[({0}) {1}{2}]}}".\
                                                 format(','.join(['_{}'.format(x) for x in self.params]),
                                                        ' '.join(['for _{0} in {0}'.format(s)
                                                                  for s in reversed(self.params)]),
                                                        self.filter_string))
                    else:
                        self.input_option.append('for_each = %s' % repr(self.params))

        def get_output(self):
            if self.prepare:
                format_string = '.format({})'.format(', '.join(['_{}'.format(s) for s in reversed(self.params)]))
                self.output_string += "{}_output = ".format(self.step.group)
                if self.step.depends:
                    self.output_string += "[sos_hash_output('{0}'{1}, prefix = '{3}', "\
                                          "suffix = '{{}}'.format({4})) {2}]".\
                                          format(' '.join([self.step.name, str(self.step.exe), self.step.group] \
                                                          + ['{0}:{{}}'.format(x) for x in reversed(self.params)]),
                                                 format_string, self.loop_string + self.filter_string, self.step.name, "':'.join(__i)")
                else:
                    self.output_string += "[sos_hash_output('{0}'{1}, prefix = '{3}') {2}]".\
                                      format(' '.join([self.step.name, str(self.step.exe), self.step.group] \
                                                      + ['{0}:{{}}'.format(x) for x in reversed(self.params)]),
                                             format_string, self.loop_string + self.filter_string, self.step.name)
            else:
                # FIXME
                output_group_by = 1
                self.output_string += "output: output_files, group_by = {}".format(output_group_by)

        def get_step_option(self):
            if not self.prepare and self.step.is_extern:
                self.step_option += "task:\n"

        def get_action(self):
            if self.prepare:
                combined_params = '[([{0}], {1}) {2}]'.\
                                  format(', '.join(["('exec', '{}')".format(self.step.name)] \
                                                   + ["('{0}', _{0})".format(x) for x in reversed(self.params)]),
                                         None if '__i' not in self.loop_string else "'{}'.format(' '.join(__i))",
                                         self.loop_string + self.filter_string)
                key = "DSC_UPDATES_['{{}}:{}'.format(sequence_id)]".format(self.name)
                self.action += "{} = OrderedDict()\n".format(key)
                if self.step.depends:
                    self.action += "for x, y in zip({}, {}_output):\n\t{}[' '.join((y, x[1]))]"\
                                  " = OrderedDict([('sequence_id', {}), "\
                                  "('sequence_name', {}), ('step_name', '{}')] + x[0])\n".\
                                  format(combined_params, self.step.group, key, 'sequence_id',
                                         'sequence_name', self.name)
                else:
                    self.action += "for x, y in zip({}, {}_output):\n\t{}[y]"\
                                   " = OrderedDict([('sequence_id', {}), "\
                                   "('sequence_name', {}), ('step_name', '{}')] + x[0])\n".\
                                   format(combined_params, self.step.group, key, 'sequence_id',
                                          'sequence_name', self.name)
                self.action += "{0}['DSC_IO_'] = ({1}, {2})\n".\
                               format(key, '[]' if self.input_vars is None else '{0} if {0} is not None else []'.\
                                      format(self.input_vars), "{}_output".format(self.step.group))
                # FIXME: multiple output to be implemented
                self.action += "{0}['DSC_EXT_'] = \'{1}\'\n".\
                               format(key, flatten_list(self.step.rf.values())[0])
            else:
                # FIXME: have not considered super-step yet
                # Create fake plugin and command list for now
                for idx, (plugin, cmd) in enumerate(zip([self.step.plugin], [self.step.exe])):
                    self.action += '{}: workdir = {}\n'.format(plugin.name, repr(self.step.workdir))
                    # Add action
                    if not self.step.shell_run:
                        script_begin = plugin.get_input(self.params, len(self.step.depends),
                                                        self.step.libpath, idx,
                                                        cmd.split()[1:] if len(cmd.split()) > 1 else None,
                                                        True if len([x for x in self.step.depends if x[2] == 'var']) else False)
                        script_begin = '{1}\n{0}\n{2}'.\
                                       format(script_begin.strip(),
                                              '## BEGIN code by DSC2',
                                              '## END code by DSC2')
                        if len(self.step.rv):
                            script_end = plugin.get_return(self.step.rv)
                            script_end = '{1}\n{0}\n{2}'.\
                                         format(script_end.strip(),
                                                '## BEGIN code by DSC2',
                                                '## END code by DSC2')
                        else:
                            script_end = ''
                        try:
                            cmd_text = [x.rstrip() for x in open(cmd.split()[0], 'r').readlines()
                                        if x.strip() and not x.strip().startswith('#')]
                        except IOError:
                            raise IOError("Cannot find script ``{}``!".format(cmd.split()[0]))
                        if plugin.name == 'R':
                            cmd_text = ["suppressMessages({})".format(x.strip())
                                        if re.search(r'^(library|require)\((.*?)\)$', x.strip())
                                        else x for x in cmd_text]
                        script = '\n'.join([script_begin, '\n'.join(cmd_text), script_end])
                        if self.try_catch:
                            script = plugin.add_try(script, len(flatten_list([self.step.rf.values()])))
                        script = """## {0} script UUID: ${{DSC_STEP_ID_}}\n{1}""".\
                                 format(str(plugin), script)
                        self.action += script
                        self.exe_signature.append(fileMD5(self.step.exe.split()[0], partial = False)
                                                  if os.path.isfile(self.step.exe.split()[0])
                                                  else self.step.exe.split()[0] + \
                                                  (self.step.exe.split()[1]
                                                   if len(self.step.exe.split()) > 1 else ''))
                    else:
                        executable(cmd.split()[0])
                        self.action += cmd

        def dump(self):
            return '\n'.join([x for x in
                              [self.header,
                               self.param_string,
                               ' '.join([self.input_string,
                                         (', ' if self.input_string != 'input:' else '') + ', '.join(self.input_option)])
                               if not self.prepare else self.input_string,
                               self.output_string,
                               self.step_option,
                               self.action]
                              if x])