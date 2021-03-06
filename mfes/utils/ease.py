import os
import numpy as np
from mfes.config_space.util import get_configuration_id
import hashlib


def ease_target(*dargs, **dkargs):
    # get model dir.
    model_dir = './data/models'
    if 'model_dir' in dkargs:
        model_dir = dkargs['model_dir']
    if not model_dir.endswith('/'):
        model_dir += '/'
    if not os.path.exists(model_dir):
        os.makedirs(model_dir)

    # get method name from kargs.
    name = 'method_name'
    if 'name' in dkargs:
        name = dkargs['name']

    def _dec(func):
        def dec(*args, **kargs):
            params = args[1]
            conf_cp = params.copy()
            needed_lc = conf_cp['need_lc']
            method_name = conf_cp['method_name']
            if 'reference' in params:
                del conf_cp['reference']
            if 'need_lc' in params:
                del conf_cp['need_lc']
            hash_cp = conf_cp.copy()
            del hash_cp["method_name"]
            conf_id = get_configuration_id(hash_cp)
            sha = hashlib.sha1(conf_id.encode('utf8'))
            conf_id = sha.hexdigest()
            ref_model_path = model_dir + '%s_%s.ckpt' % (method_name, conf_id)
            model_path = ref_model_path
            if 'reference' in params:
                ref_model_path = model_dir + '%s_%s.ckpt' % (method_name, params['reference'])
            conf_cp['read_path'] = ref_model_path
            conf_cp['save_path'] = model_path
            conf_cp['need_lc'] = needed_lc
            try:
                result = func(args[0], conf_cp, kargs)
            except:
                result = {'loss': np.inf, 'early_stop': False, 'lc_info': []}

            if 'ref_id' not in result:
                result['ref_id'] = conf_id
            return result

        return dec

    return _dec
