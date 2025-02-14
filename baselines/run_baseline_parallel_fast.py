from os.path import exists
from pathlib import Path
import uuid
from red_gym_env import RedGymEnv
from stable_baselines3 import PPO
from stable_baselines3.common import env_checker
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv
from stable_baselines3.common.utils import set_random_seed
from stable_baselines3.common.callbacks import CheckpointCallback, CallbackList
from tensorboard_callback import TensorboardCallback
import numpy

def load_file(file):
    files = {
        "0": '',
        "1": 'session_e41c9eff/poke_38207488_steps', #default
        "A": 'session_62a584f7/poke_4423680_steps', #A: 4.4
        "B": 'session_1ccee64f/poke_14417920_steps', # A ->, 4.4 mil
        "C": 'session_1ccee64f/poke_14417920_steps', # B ->, 12.7 mil
        "D": 'session_d7bf13d8/poke_1105920_steps', # C ->, CPU = 6, ep_multi = 30
        "E": 'session_90efa56b/poke_6144_steps', # D ->, CPU = 12, 512 steps
        "F": 'session_dbd6c431/poke_114688_steps', # E ->, 3.5k step per epoch first save
        "G": 'session_99f314e8/poke_4751360_steps', # F ->, 5k steps per epoch
        "H": 'session_41b581ec/poke_7208960_steps', # G ->, 10k steps
        "I": 'session_f46b8c7a/poke_57344_steps', #I
        "J": 'session_04f3bcfd/poke_409600_steps',
        "K": 'session_3f0b27ce/poke_425984_steps',
        "512": 'session_7b47178a/poke_1024000_steps',
        "5120": 'session_1afae984/poke_3686400_steps', # K ->, 5k steps
        "N": '',
        "O": '',
        "P": '',
        "K": '',
        "K": '',
    }
    return files.get(file, "Invalid File.")

def make_env(rank, env_conf, seed=0):
    """
    Utility function for multiprocessed env.
    :param env_id: (str) the environment ID
    :param num_env: (int) the number of environments you wish to have in subprocesses
    :param seed: (int) the initial seed for RNG
    :param rank: (int) index of the subprocess
    """
    def _init():
        env = RedGymEnv(env_conf)
        env.reset(seed=(seed + rank))
        return env
    set_random_seed(seed)
    return _init

sess_id = str(uuid.uuid4())[:8]
sess_path = Path(f'session_{sess_id}')

if __name__ == '__main__':
    # Load which file to start training from, "0" = none
    use_wandb_logging = True
    file_name = load_file("C")
    endless = True

    cpu_dynamic = False
    max_num_cpu = 16
    cpu_multi = 1000
    num_cpu = 16 # Starting CPU

    epoch_base = 512
    epoch_multi = 10
    learn_steps = 60
    
    reward_multi = 3
    explore_multi = 1
    simulated_frame = 2_000_000.0

    while num_cpu <= max_num_cpu and endless == True:
        epoch_length = epoch_base * epoch_multi
        env_config = {
                'headless': True, 'save_final_state': True, 'early_stop': False,
                'action_freq': 24, 'init_state': '../has_pokedex_nballs.state', 'max_steps': epoch_length, 
                'print_rewards': True, 'save_video': False, 'fast_video': True, 'session_path': sess_path,
                'gb_path': '../PokemonRed.gb', 'debug': False, 'sim_frame_dist': simulated_frame, 
                'use_screen_explore': True, 'reward_scale': reward_multi, 'extra_buttons': False,
                'explore_weight': explore_multi
            }

        print(env_config)
        env = SubprocVecEnv([make_env(i, env_config) for i in range(num_cpu)])

        checkpoint_callback = CheckpointCallback(save_freq=epoch_length, save_path=sess_path, name_prefix='poke')

        callbacks = [checkpoint_callback, TensorboardCallback()]

        if use_wandb_logging:
            import wandb
            from wandb.integration.sb3 import WandbCallback
            run = wandb.init(
                project="pokemon-train",
                id=sess_id,
                config=env_config,
                sync_tensorboard=True,
                monitor_gym=True,  
                save_code=True,
            )
            callbacks.append(WandbCallback())

        for i in range(learn_steps):
            while True:  # Keep retrying until successful or until epoch_multi becomes too small
                try:
                    if exists(file_name + '.zip'):
                        print('\nloading checkpoint')
                        model = PPO.load(file_name, env=env)
                        model.n_steps = epoch_length
                        model.n_envs = num_cpu
                        model.rollout_buffer.buffer_size = epoch_length
                        model.rollout_buffer.n_envs = num_cpu
                        model.rollout_buffer.reset()
                    else:
                        model = PPO('CnnPolicy', env, verbose=1, n_steps=epoch_length, batch_size=128, n_epochs=3, gamma=0.998)
            
                    model.learn(total_timesteps=(epoch_length)*num_cpu*cpu_multi // 8, callback=CallbackList(callbacks))

                    if use_wandb_logging:
                        run.finish()

                    break  # Exit the while loop if everything was successful

                except numpy.core._exceptions._ArrayMemoryError:  # Catch memory errors
                    print(f"\nMemoryError encountered during training!")
                    print(f"Reducing epoch_multi from {epoch_multi} to {epoch_multi - 1}")
                    epoch_multi -= 1  # Reduce epoch_multi
                    if epoch_multi <= 0:
                        raise RuntimeError("epoch_multi became zero or negative. Cannot proceed further.")
                    epoch_length = 2048 * epoch_multi  # Update epoch_length
                    env_config['max_steps'] = epoch_length  # Update env_config
                    env = SubprocVecEnv([make_env(i, env_config) for i in range(num_cpu)])  # Recreate env

            # If cpu_dynamic is True, modify num_cpu and epoch_multi for the next epoch
            if cpu_dynamic:
                if num_cpu < max_num_cpu:
                    num_cpu += 1
                #epoch_multi += 1



