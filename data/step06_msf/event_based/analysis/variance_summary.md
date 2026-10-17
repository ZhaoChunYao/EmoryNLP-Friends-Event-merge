# Scene vs Episode Variance Summary

- episode variance: variance over subscene scores within each episode/character/trait
- scene variance: variance over scene-aggregated mean scores within each episode/character/trait
- variance uses population variance (ddof=0)

- overall mean episode variance: **0.404851**
- overall mean scene variance: **0.312278**
- scene minus episode: **-0.092573**

## Output files

- `variance_per_episode_character_trait.csv`
- `variance_mean_per_character_trait.csv`
- `variance_mean_per_character.csv`
- `variance_overall_summary.json`