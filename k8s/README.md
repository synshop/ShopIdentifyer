# Deploying ShopIdentifyer to k3s

These manifests run ShopIdentifyer as a single pod on a single-node k3s
cluster. The app talks to the MySQL server running on the k3s host, and
k3s's bundled Traefik routes outside traffic to it.

| File | What it does |
| --- | --- |
| `deployment.yaml` | Runs the app pod, with `config.py` mounted from a Secret |
| `service.yaml` | Gives the app pod a stable in-cluster address |
| `ingress.yaml` | Routes `shopidentifyer.192.168.4.109.nip.io` to the app |
| `mysql-external.yaml` | Lets the app reach the host's MySQL as `mysql:3306` |

Everything lives in the `shopidentifyer` namespace.

## Deploying a new version

Run these from the repository root, on the branch you want to deploy, on
the k3s host.

### 1. Pick the next version

Look up the tag that's running now and choose the next one:

    kubectl -n shopidentifyer get deploy shopidentifyer \
      -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'

    VERSION=0.1.3

Always use a new tag. The deployment uses `imagePullPolicy: IfNotPresent`,
so reusing a tag can leave the old image running.

### 2. Build the image

The image is built from your working tree, so commit or stash anything
you don't want in it first. `identity/config.py` is never copied into the
image (see `.dockerignore`).

    docker build -t shopidentifyer:$VERSION .

### 3. Import the image into k3s

k3s runs its own containerd and can't see Docker's images. Importing needs
root:

    docker save shopidentifyer:$VERSION | sudo k3s ctr images import -

Check that it arrived:

    sudo k3s ctr images ls -q | grep shopidentifyer

### 4. Apply any database changes

If this version adds or changes columns, run the matching
`sql/upgrade-*.sql` script against the database **before** rolling out. The
new code expects the new columns. For example:

    mysql -u root -p < sql/upgrade-members-vetting-doc.sql

Each upgrade script runs once. Running one again fails with a
"Duplicate column" error, which is harmless.

### 5. Roll out

Set the new tag in `deployment.yaml`, then apply it and wait:

    sed -i "s/image: shopidentifyer:.*/image: shopidentifyer:$VERSION/" k8s/deployment.yaml
    kubectl apply -f k8s/deployment.yaml
    kubectl -n shopidentifyer rollout status deploy/shopidentifyer

The deployment uses the `Recreate` strategy, so the old pod stops before
the new one starts. Expect a few seconds of downtime. Only one pod may run
at a time, because the scheduled jobs (Stripe cache rebuild, members
refresh, offboarding report) run inside the app.

Commit the tag change so `deployment.yaml` matches what's running.

### 6. Check it

    kubectl -n shopidentifyer get pods
    kubectl -n shopidentifyer logs deploy/shopidentifyer --tail=50

The pod should be `Running` with 0 restarts, and the logs should show
`SYN Shop Id Started...` with no errors. Then log in at
<http://shopidentifyer.192.168.4.109.nip.io> and look at the pages the
change touched.

## Rolling back

The previous image stays in k3s, so you can go back to the last version:

    kubectl -n shopidentifyer rollout undo deploy/shopidentifyer

Then set the old tag back in `deployment.yaml`. Rolling back doesn't undo
database changes. Added columns are harmless to older code, so you
usually don't need to.

## Changing configuration

`config.py` and the encryption key live in two Secrets:

| Secret | Key | Used as |
| --- | --- | --- |
| `shopidentifyer-config` | `config.py` | Mounted at `/app/identity/config.py` |
| `shopidentifyer-key` | `ENCRYPTION_KEY` | Environment variable that unlocks the `ENCRYPTED_*` values |

To change the config, update the Secret from your local copy and restart
the pod. The file is mounted with `subPath`, so a running pod doesn't pick
up the change on its own.

    kubectl -n shopidentifyer create secret generic shopidentifyer-config \
      --from-file=config.py=identity/config.py \
      --dry-run=client -o yaml | kubectl apply -f -
    kubectl -n shopidentifyer rollout restart deploy/shopidentifyer

## First-time setup

On a fresh cluster, create the namespace and both Secrets before applying
the manifests:

    kubectl create namespace shopidentifyer
    kubectl -n shopidentifyer create secret generic shopidentifyer-config \
      --from-file=config.py=identity/config.py
    kubectl -n shopidentifyer create secret generic shopidentifyer-key \
      --from-literal=ENCRYPTION_KEY='<the encryption key>'

Then build and import an image (steps 1 to 3 above) and apply everything:

    kubectl apply -f k8s/

In `config.py`, set `DATABASE_HOST = 'mysql'`. MySQL on the host must
listen on the cni0 bridge address (`10.42.0.1`) and allow the `synshop`
user to connect from the pod network (`10.42.%`).
