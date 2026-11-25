"""Score the frozen v1.43 release against disclosed 2026 actuals; no tuning."""
import argparse,json
from skill_regressed_release_v1_43 import evaluate
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k,v in dict(release='outputs/skill_regressed_release_v1_43',
        labels='outputs/training_labels_v1_0',evaluation='outputs/pitcher_evaluation_v1_29',
        output='outputs/skill_regressed_release_v1_43_evaluation',backup_root='backups').items():
        p.add_argument('--'+k.replace('_','-'),default=v)
    print(json.dumps(evaluate(p.parse_args()),indent=2))
