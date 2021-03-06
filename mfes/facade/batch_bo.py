import numpy as np
import time
import random
from math import log, ceil
from mfes.model.rf_with_instances import RandomForestWithInstances
from mfes.utils.util_funcs import get_types
from mfes.acquisition_function.acquisition import EI
from mfes.optimizer.random_sampling import RandomSampling
from mfes.config_space import convert_configurations_to_array, sample_configurations
from mfes.config_space.util import expand_configurations
from mfes.facade.base_facade import BaseFacade


class SMAC(BaseFacade):

    def __init__(self, config_space, objective_func, R,
                 num_iter=10, n_workers=1, eta=3, random_state=1, method_id="Default"):
        BaseFacade.__init__(self, objective_func, n_workers=n_workers, method_name=method_id)
        self.config_space = config_space
        self.seed = random_state
        self.config_space.seed(self.seed)
        self.R = R
        self.num_iter = num_iter
        self.eta = eta
        self.logeta = lambda x: log(x) / log(self.eta)
        self.s_max = int(self.logeta(R))
        self.inner_iteration_n = (self.s_max + 1) * (self.s_max + 1)

        types, bounds = get_types(config_space)
        self.num_config = len(bounds)
        self.surrogate = RandomForestWithInstances(types=types, bounds=bounds)
        self.acquisition_func = EI(model=self.surrogate)
        # TODO: add SMAC's optimization algorithm.
        self.acq_optimizer = RandomSampling(self.acquisition_func, config_space,
                                            n_samples=max(500, 50 * self.num_config))

        self.incumbent_configs = []
        self.incumbent_obj = []
        self.p = 0.3

    def iterate(self):
        n_loop = int(ceil(1.0 * self.inner_iteration_n / self.num_workers))
        for _ in range(n_loop):
            T = self.choose_next(self.num_workers)
            extra_info = None

            ret_val, early_stops = self.run_in_parallel(T, self.R, extra_info)
            val_losses = [item['loss'] for item in ret_val]
            self.incumbent_configs.extend(T)
            self.incumbent_obj.extend(val_losses)
            self.add_stage_history(self.stage_id, self.global_incumbent)
            self.stage_id += 1
            self.remove_immediate_model()

    @BaseFacade.process_manage
    def run(self):
        try:
            for iter in range(self.num_iter):
                self.logger.info('-' * 50)
                self.logger.info("SMAC algorithm: %d/%d iteration starts" % (iter, self.num_iter))
                start_time = time.time()
                self.iterate()
                time_elapsed = (time.time() - start_time) / 60
                self.logger.info("iteration took %.2f min." % time_elapsed)
                self.save_intemediate_statistics()
        except Exception as e:
            print(e)
            self.logger.error(str(e))
            # clear the immediate result.
            self.remove_immediate_model()

    def choose_next(self, num_config):
        if len(self.incumbent_obj) < 3:
            return sample_configurations(self.config_space, num_config)

        self.logger.info('BO Training - X: %s' % str(self.incumbent_configs[-5:]))
        self.logger.info('BO Training - Y: %s' % str(self.incumbent_obj))
        self.surrogate.train(convert_configurations_to_array(self.incumbent_configs),
                             np.array(self.incumbent_obj, dtype=np.float64))

        conf_cnt = 0
        total_cnt = 0
        _next_configs = []
        while conf_cnt < num_config and total_cnt < 5 * num_config:
            incumbent = dict()
            best_index = np.argmin(self.incumbent_obj)
            incumbent['obj'] = self.incumbent_obj[best_index]
            incumbent['config'] = self.incumbent_configs[best_index]

            self.acquisition_func.update(model=self.surrogate, eta=incumbent)
            rand_config = self.acq_optimizer.maximize(batch_size=1)[0]
            if rand_config not in _next_configs:
                _next_configs.append(rand_config)
                conf_cnt += 1
            total_cnt += 1
        if conf_cnt < num_config:
            _next_configs = expand_configurations(_next_configs, self.config_space, num_config)

        next_configs = []

        # Epsilon greedy
        for config in _next_configs:
            if random.random() < self.p:
                next_configs.append(sample_configurations(self.config_space, 1)[0])
            else:
                next_configs.append(config)

        return next_configs

    def get_incumbent(self, num_inc=1):
        assert (len(self.incumbent_obj) == len(self.incumbent_configs))
        indices = np.argsort(self.incumbent_obj)
        configs = [self.incumbent_configs[i] for i in indices[0:num_inc]]
        targets = [self.incumbent_obj[i] for i in indices[0: num_inc]]
        return configs, targets
