# Nebius: one-time setup

We train on Nebius serverless GPU jobs (an L40S), as in norma-core's own
[`software/ai/smolvla_py/nebius.md`](https://github.com/norma-core/norma-core/blob/main/software/ai/smolvla_py/nebius.md).
Do this once, on the laptop that will submit the job. Credentials stay on your machine:
never commit them.

1. **Nebius CLI.** Install it from the Nebius docs (<https://docs.nebius.com/cli/install>), then create a profile and log in. This opens your browser:

   ```bash
   nebius profile create
   ```

2. **Bucket** for the code bundle, the dataset and the checkpoints:

   ```bash
   nebius storage bucket create --name third-hand-vla
   ```

   ```bash
   nebius storage bucket list
   ```

   Note the bucket id (`storagebucket-...`) and the region (for example `eu-north1`).

3. **s5cmd** for uploads, with a `nebius` profile:
   - In the Nebius console, create an access key for object storage.
   - Put the key in `~/.aws/credentials` under `[nebius]`, as `aws_access_key_id` and `aws_secret_access_key`.

   ```bash
   brew install peak/tap/s5cmd
   ```

4. **`vla/nebius/nebius.env`** (git-ignored):

   ```bash
   NEBIUS_BUCKET=third-hand-vla
   NEBIUS_BUCKET_ID=storagebucket-xxxxxxxx
   NEBIUS_REGION=eu-north1
   ```

5. **Dry run before the real data:** submit the fake dataset with 100 steps. This checks the whole cloud path in a few minutes:

   ```bash
   bash vla/py.sh vla/make_fake_dataset.py --output vla/data/fake.parquet
   ```

   ```bash
   STEPS=100 SAVE_EVERY=100 bash vla/nebius/submit.sh vla/data/fake.parquet
   ```

   ```bash
   nebius ai job list
   ```

The real run (about 10k steps, batch 64) is `bash vla/nebius/submit.sh vla/data/resistor.parquet`.
NormaCore's example allows it 6 hours; checkpoints land every 2,000 steps, so you can test
`step-004000` on the arm while the job is still running.
