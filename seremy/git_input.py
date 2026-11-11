"""Git commands used to inspect input repositories without input-selected helpers."""
import os
import subprocess


def run_git(arguments, **options):
    environment = {key: value for key, value in os.environ.items()
                   if not key.upper().startswith('GIT_')}
    environment.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_ATTR_NOSYSTEM='1', GIT_TERMINAL_PROMPT='0')
    command = ['git', '-c', 'core.fsmonitor=false', '-c', 'core.untrackedCache=false',
               '-c', 'core.hooksPath=', '-c', 'init.templateDir=',
               '-c', 'protocol.file.allow=never', '-c', 'protocol.ext.allow=never',
               *arguments]
    return subprocess.run(command, env=environment, **options)
