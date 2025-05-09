from trainers.n2n_trainer import train_n2n
from trainers.n2v_trainer import train_n2v
from trainers.n2s_trainer import train_n2s
from trainers.ssm_trainer import train_ssm
from trainers.pfn_trainer import train_pfn

schemas = {
    'n2n': train_n2n,
    'n2v': train_n2v,
    'n2s': train_n2s,
    'ssm': train_ssm,
    'pfn': train_pfn,
}

schema = list(schemas.keys())[2]
print(schema)

patient_count = 1

override_dict = {
    "training" : {
        "ablation": f"patient_count/{patient_count}_patients",
        "n_images_per_patient": 20,
        "n_patients" : 1,
        "load" : False
        }
    }

train_n2_base = False
train_ssm_base = False
train_proposed = False

if train_n2_base:
    schemas[schema](r"C:\Users\CL-11\OneDrive\Repos\OCTDenoisingFinal\configs\n2_config.yaml", False, override_dict)
if train_ssm_base:
    schemas[schema](r"C:\Users\CL-11\OneDrive\Repos\OCTDenoisingFinal\configs\n2_config.yaml", True, override_dict)

prog_override_dict = {
    "train" : {
        "ablation": f"patient_count/{patient_count}_patients",
        "n_patients" : 1,
        "load" : False
        }
    }

override_dict['eval'] = override_dict['training']
prog_override_dict['eval'] = prog_override_dict['train']

schema = list(schemas.keys())[4]
if train_proposed:
    schemas[schema](r"C:\Users\CL-11\OneDrive\Repos\OCTDenoisingFinal\configs\pfn_config.yaml", override_dict)

from scripts.evaluate_avg import main

patient_count = 1

eval_override = {
    "prog_config": prog_override_dict,
    "n2_eval": override_dict,
}

main(eval_override)