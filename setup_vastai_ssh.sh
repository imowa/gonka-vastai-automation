#!/bin/bash
echo "Setting up Vast.ai SSH access..."

# Your public key
SSH_PUB_KEY="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDvfUc1E+f0FVG90xO7/UliFWzmJwBS8HIBbM/+OOTWFQe3SReXbfOeak0quLFBBhFaAR1bATrU6BR2fXt+fqZzem7pd9kfq38ASPAuBF8ep0piwVMxQTWYcjSS7CPNTjka4Z3Xhy02LuCmJKQ4HY6L3fADhQkzjF0f5Ojoy0xmtXlQ3LaD2sWdZYcDBnWHpEtjj1266NTaHxCQDq8hNcBI/98vn3ZCywV/GuztLvAvwCVlRzBxn9V1jUEMz9/AE13hqv8iiBFbxc4CETis52SuG+bgawfivt9jCD7aHJLbYTxCMEs7yIyREf7ttKMPEDUcMtRyeSnLVBggkgNR8Gz/3tPb5NB7WrckX40EJzlWNh/SV9nwcNkBH4qeAVZfEXw0QHKbe5mF8WV3FMDn7o4ZrKpGiMFYzYxuNZ+SGiwMVc9NInidyWmqE9jDemyu9ouCFOtgT5DUH3e+qxmUdVTcOnqzvmpk9W5CLVkzvczN29na9rgb678ZQC/kX9ZkNj6LQl8ExA7wSrK742Jyyr0RGMcaiZ9wnB5CNu30uuBpaRJe81xhJ7g7Rzr+8QEezC+nt5r57gwrr2SYoCO/O/8XQWpOO+jaY2i7wR5Cor7h0KxBqhXzF5YWYXSTth604HzxbEBy6ApcQA7vYiTP0VeWFDsuD69f24cU/CSKqIpc1Q== root@ubuntu-s-4vcpu-16gb-amd-nyc3-01"

echo "
To add this SSH key to Vast.ai:

1. Go to: https://cloud.vast.ai/account/
2. Click on 'SSH Keys' tab
3. Click 'Add SSH Key'
4. Paste this key:

$SSH_PUB_KEY

5. Save

Once done, you'll be able to SSH into rented instances!
"
