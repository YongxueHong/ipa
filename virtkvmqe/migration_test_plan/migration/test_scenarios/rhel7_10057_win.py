from __future__ import division
from utils_host import HostSession
from monitor import RemoteQMPMonitor
import re
import os
import time
from vm import CreateTest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname
                                           (os.path.dirname
                                            (os.path.dirname
                                             (os.path.abspath(__file__))))))

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    incoming_port = str(params.get('incoming_port'))
    qmp_port = int(params.get('qmp_port'))

    test = CreateTest(case_id='rhel7_10057_win', params=params)
    id = test.get_id()
    downtime = '30000'
    script = 'migration_dirtypage_1.c'
    query_timeout = 2400
    active_timeout = 300
    running_timeout = 300

    src_host_session = HostSession(id, params)
    src_qemu_cmd = params.create_qemu_cmd()

    test.main_step_log('1. Start VM in src host ')
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.sub_step_log('Wait 90s for guest boot up')
    time.sleep(90)

    test.main_step_log('2. Start listening mode in dst host ')
    incoming_val = 'tcp:0:%s' % (incoming_port)
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(ip=dst_host_ip, cmd=dst_qemu_cmd,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)

    test.main_step_log('3. src guest have '
                       'programme running to generate dirty page --- skip for windows guest')

    test.main_step_log('4. Migrate to the destination')
    cmd = '{"execute":"migrate", "arguments": {"uri": "tcp:%s:%s"}}' % \
          (dst_host_ip, incoming_port)
    src_remote_qmp.qmp_cmd_output(cmd)

    test.main_step_log('5.set downtime for migration')
    flag_active = False
    cmd = '{"execute":"query-migrate"}'
    end_time = time.time() + active_timeout
    while time.time() < end_time:
        output = src_remote_qmp.qmp_cmd_output(cmd)
        if re.findall(r'"status": "active"', output):
            flag_active = True
            break
        elif re.findall(r'"status": "failed"', output):
            src_remote_qmp.test_error('Migration failed')
    if (flag_active == False):
        src_remote_qmp.test_error('Migration could not be active within %d'
                                  % active_timeout)

    downtime_cmd = '{"execute":"migrate-set-parameters",' \
                   '"arguments":{"downtime-limit": %s}}' % downtime
    src_remote_qmp.qmp_cmd_output(cmd=downtime_cmd)
    paras_chk_cmd = '{"execute":"query-migrate-parameters"}'
    output = src_remote_qmp.qmp_cmd_output(cmd=paras_chk_cmd)
    if re.findall(r'"downtime-limit": %s' % downtime, output):
        test.test_print('Set migration downtime successfully')
    else:
        test.test_error('Failed to change downtime')

    test.sub_step_log('Check the status of migration')
    flag = False
    cmd = '{"execute":"query-migrate"}'
    end_time = time.time() + query_timeout
    while time.time() < end_time:
        output = src_remote_qmp.qmp_cmd_output(cmd=cmd)
        if re.findall(r'"remaining": 0', output):
            flag = True
            break
        elif re.findall(r'"status": "failed"', output):
            src_remote_qmp.test_error('migration failed')

    if (flag == False):
        test.test_error('Migration timeout in %d' % query_timeout)

    test.main_step_log('6.Check status of guest in dst host')
    cmd = '{"execute":"query-status"}'
    flag_running = False
    end_time = time.time() + running_timeout
    while time.time() < end_time:
        output = dst_remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=3)
        if re.findall(r'"status": "running"', output):
            flag_running = True
            break

    if (flag_running == False):
        test.test_error('Dst guest is not running after migration finished %d '
                        'seconds' % running_timeout)

    test.sub_step_log('quit qemu on src end and shutdown vm on dst end')
    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}',
                                           recv_timeout=3)
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src host')

    output = dst_remote_qmp.qmp_cmd_output('{"execute":"quit"}')
    if output:
        dst_remote_qmp.test_error('Failed to quit qemu on dst end')
