# How to run ansible

1. Provision instance on GCP and establish an ssh key
`gcloud compute ssh --zone <zone> <instance-name>`.

2. Once you have an ssh connection to the servers, add their IPs
to `inventory.yaml` like the following.

```
[web]
<server-name> ansible_host=<server-ip-addr>

[database]
<server-name> ansible_host=<server-ip-addr>
```

3. Install ansible and download dependencies
```
python3 -m pip install --user ansible
ansible-galaxy install geerlingguy.postgresql davidwittman.redis
```

4. Run the setup playbooks. This secures the servers, installs postgresql, redis, python, among other things.
```
ansible-playbook ./playbooks/setup.yaml -i inventory.yaml
ansible-playbook ./playbooks/web.yaml -i inventory.yaml
```

5. Run the deploy playbook. This requires you have a GitHub SSH key authorized to clone this repo.
See [docs](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/adding-a-new-ssh-key-to-your-github-account?tool=cli#about-addition-of-ssh-keys-to-your-account) for how to add one.

```
ansible-playbook ./playbooks/deploy.yaml -i inventory.yaml
```
