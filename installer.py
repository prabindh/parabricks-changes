#!/usr/bin/env python

import argparse
import subprocess
import sys
import os
import errno
import textwrap
import shutil
import time
from distutils.dir_util import copy_tree

NVIDIA_DOCKER = "docker"
#NVIDIA_DOCKER = "nvidia-docker"

def GetUserDecision():
  inputVar = input
  try:
    inputVar = raw_input
  except NameError:
    pass
  agreement = inputVar("Proceed with installation? Type yes or no only: ")
  while agreement != "yes"  and agreement != "no":
    agreement = inputVar("Type yes or no only: ")
  print("")
  return agreement


def GetUserAgreement():
  agreement = GetUserDecision()
  if agreement == "no":
    print("\nInstallation Aborted\n")
    print("python installery.py -h to see available installation options")
    print("If you have not received EULA.txt or have any other questions")
    print("Contact Parabricks-Support@nvidia.com for any questions\n")
    sys.exit(0)

def GetEULAAgreement(scriptDir, runArgs):
  if os.path.isfile(scriptDir + "/EULA.txt") == False:
    print("Inconsistent Installation Package. EULA.txt not found. Exiting...")
    InstallAbort()

  with open(scriptDir + "/EULA.txt", "r") as eula_file:
    eula_string = eula_file.readline()
    while eula_string:
      print(textwrap.fill(eula_string, 120))
      eula_string = eula_file.readline()

  print(textwrap.fill("The software can be used only with the above End User License Agreement stated above.", 120))
  if runArgs.force == False:
    GetUserAgreement()

def GetFullDirPath(dirName):
  if dirName == None:
    OptError("A required directory name cannot be empty")
  dirName = dirName + "/"
  if os.path.isabs(dirName):
    return os.path.abspath(os.path.dirname(dirName))
  else:
    return os.path.abspath(os.path.dirname(os.getcwd() + '/' + dirName))

def GetHostFile(inputName):
  if os.path.isabs(inputName):
    return inputName
  else:
    return os.path.abspath(os.getcwd() + '/' + inputName)

def InstallAbort():
  print("Contact support@parabricks.com for troubleshooting")
  if install_args.container == "docker":
    if subprocess.call("command -v docker", shell=True) == 0:
      if install_args.ngc == False:
        subprocess.call(["docker", "logout", "registry.gitlab.com"])
  os.chdir(currentDir)
  sys.exit(-1)


def run_and_return(cmd_line, err_mesg, shell_var=False, on_screen=False, environ=os.environ.copy()):
  #print cmd_line
  cmd_log_file = log_file
  if on_screen == True:
    cmd_log_file = None
  log_file.write("+ " + " ".join(cmd_line) + "\n")
  log_file.flush()
  cmd_return_code = subprocess.call(cmd_line, stdout = cmd_log_file, stderr = cmd_log_file, shell=shell_var, env=environ)
  if  cmd_return_code != 0:
    print(err_mesg)
    InstallAbort()
  return 0

def remove_images(install_args, blacklist):
  cmd_proc = subprocess.Popen(["docker", "images"], stdout = subprocess.PIPE, universal_newlines=True)
  installed_image = cmd_proc.stdout.readline()
  while installed_image:
    if installed_image[:18] == "parabricks/release":
      installed_image_list = installed_image.split()
      if installed_image_list[1] in blacklist:
        installed_image = cmd_proc.stdout.readline()
        continue
      print("Removing older image: " + "parabricks/release:" + installed_image_list[1])
      run_and_return(["docker", "rmi", "parabricks/release:" + installed_image_list[1]], "Could not uninstall all images")
    installed_image = cmd_proc.stdout.readline()
  print("\n")

def uninstall_pbrun(install_args):
  if install_args.container == "docker":
    remove_images(install_args,[])

  install_folder = install_args.install_location + "/parabricks"
  if os.path.exists(install_folder):
    shutil.rmtree(install_folder)

  try:
    if os.path.lexists("/usr/bin/pbrun"):
      os.unlink("/usr/bin/pbrun")
  except OSError as exc:
    print("Could not remove /usr/bin/pbrun. Permission denied")

  print("Parabricks uninstalled from " + install_args.install_location)


def check_curl():
  print("Checking curl installation\n")
  run_and_return ("command -v curl", "curl --version failed. Please check installation of curl.", True)

def check_nvidia_docker(archImage):
  cmd_return_code = subprocess.call("command -v "+NVIDIA_DOCKER, stdout = log_file, stderr = log_file, shell=True)
  if  cmd_return_code != 0:
    return False
  cmd_return_code = subprocess.call([NVIDIA_DOCKER, "run", "--rm", "--gpus", "all", "nvidia/cuda" + archImage + ":9.0-base-ubuntu16.04", "nvidia-smi"] , stdout = log_file, stderr = log_file)
  if  cmd_return_code != 0:
    return False
  else:
    return True

def check_docker(cpu_only):
  archImage = ""
  if install_args.arch == "ppc64le":
    archImage = "-ppc64le"

  if check_nvidia_docker(archImage) == True:
    return NVIDIA_DOCKER

  print("Checking docker installation\n")
  run_and_return("command -v docker", "docker not found. Please check installation of docker.", True)
  if cpu_only:
    return "docker"
  else:
    print(textwrap.fill("Error in docker installation. Check install log in tmp folder", 120))

def check_singularity():
  print("Checking singularity installation\n")
  run_and_return("command -v singularity", "singularity not found. Please check singularity installation", True)
  run_and_return(["singularity", "--version"], "singularity --version failed. Please check installation of singularity.")
  cmd_proc = subprocess.Popen(["singularity", "--version"], stdout = subprocess.PIPE, universal_newlines=True)
  singularity_version = cmd_proc.stdout.readline().split('.')
  if "singularity version " in singularity_version[0]:
    if os.getuid() != 0:
      print(textwrap.fill("You need root permissions to install with singularity v3.x or higher. Try with sudo, or install on a machine with sudo and copy the parabricks folder, or contact system administrator", 120))
      InstallAbort()
    return "singularity 3.x"
  if (int(singularity_version[0]) < 2) and (int(singularity_version[1]) < 5) and (int(singularity_version[1]) < 2) :
    print("Singularity version 2.5.2 or higher required")
    InstallAbort()
  return "singularity 2.x"

def check_requirements(cpu_only):
  runCmd = ""
  check_curl()
  if install_args.container == "singularity":
    runCmd = check_singularity()
  else:
    runCmd = check_docker(cpu_only)
  return runCmd

def check_image_pre_install():
  print("Checking if image is already present\n")
  release_full_name = "registry.gitlab.com/pbuser/release/" + install_args.arch + ":" + install_args.release
  if install_args.ngc == True:
    release_full_name = "nvcr.io/hpc/parabricks:" + install_args.release

  cmd_return_code = subprocess.call(["docker", "inspect", "--type=image", release_full_name], stdout = log_file, stderr = log_file)
  if  cmd_return_code == 0:
    print("Docker image already present, please remove the docker image: " + release_full_name + " and then try re-installation")
    print("\nRun\ndocker rmi " + release_full_name + "\nto remove the image. Make sure you really want to do this.")
    InstallAbort()

  cmd_return_code = subprocess.call(["docker", "inspect", "--type=image", "parabricks/release:" + install_args.release], stdout = log_file, stderr = log_file)
  if  cmd_return_code == 0:
    print("Docker image already present, please remove the docker image: parabricks/release: " + install_args.release  + " and then try re-installation")
    print("\nRun\ndocker rmi parabricks/release:" + install_args.release + "\nto remove the image. Make sure you really want to do this.")
    InstallAbort()


def print_selection(allArgs):
  print("====================================")
  print("Installing Parabricks")
  print("Final Selection:")
  print("Install Directory:      " + allArgs.install_location)
  print("Install Version:        " + allArgs.release)
  print("Install Container Type: " + allArgs.container)
  print("Install Architecture:   " + allArgs.arch)
  print("Registry:               " + "nvcr.io" if (allArgs.ngc == True)  else "registry.gitlab.com")
  print("====================================\n")
  print
  if allArgs.force == False:
    print(textwrap.fill("Are the above installation parameters correct?", 120))
    GetUserAgreement()
    print(textwrap.fill("Do you want to create a symlink to /usr/bin/pbrun ?", 120))
    if GetUserDecision() == "yes":
      allArgs.symlink = True
    else:
      allArgs.symlink = False

def get_install_args():
  parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("--release", help="Target version of DNA Bricks", default="v2.5.0")
  parser.add_argument("--install-location", help="Installation location for parabricks", default="/opt/")
  parser.add_argument("--arch", help=argparse.SUPPRESS, default=None, choices=[None, "x86_64", "ppc64le"])
  parser.add_argument("--container", help=argparse.SUPPRESS, default="docker", choices=["docker", "singularity"])
  parser.add_argument("--access-token", help=argparse.SUPPRESS, default="ma-n1NazFEnDDwpoc-a2")
  parser.add_argument("--uninstall", help="Remove all parabricks installations", action='store_true', default=False)
  parser.add_argument("--symlink", help="Create symlink for /usr/bin/pbrun", action='store_true', default=False)
  parser.add_argument("--force", help="Disable interactive installation", action='store_true', default=False)
  parser.add_argument("--ngc", help="Pull image from NGC", action='store_false', default=True)
  parser.add_argument("--cpu-only", help="Install CPU only accelerated tools", action='store_true', default=False)
  allArgs = parser.parse_args()
  if allArgs.uninstall == True:
    print("Starting Uninstallation\n")
    return allArgs

  allArgs.install_location = GetFullDirPath(allArgs.install_location) + "/parabricks"
  cmd_proc = subprocess.Popen(["uname", "-m"], stdout = subprocess.PIPE, universal_newlines=True)
  if allArgs.arch == None:
    sys_arch = cmd_proc.stdout.readline().rstrip('\n')
    print(sys_arch)
    if (sys_arch != "x86_64") and (sys_arch != "ppc64le"):
      print("Unsupported architecture " + sys_arch + ". Exiting...")
      InstallAbort()
    else:
      allArgs.arch = sys_arch
  return allArgs

def check_install_folder(install_folder):
  if not os.path.exists(install_folder):
    try:
      os.makedirs(install_folder)
    except OSError as exc:
      if exc.errno == errno.EEXIST and os.path.isdir(install_folder):
        pass
      else:
        print("\nPlease check you have permissions to create parabricks folder in " + install_folder)
        InstallAbort()
  elif os.path.exists(install_folder + "/parabricks"):
    print(install_folder + "/parabricks already exists. Please remove it and try installation again")
    InstallAbort()

  if os.access(install_folder, os.W_OK) == False:
    print("\nPlease check you have write permissions in " + install_folder)
    InstallAbort()

def install_docker_image():
  check_image_pre_install()
  os.chdir(install_args.install_location)
  print("\nDownloading image\n")
  image_full_name = "parabricks/release:" + install_args.release
  release_full_name = "registry.gitlab.com/pbuser/release/" + install_args.arch + ":" + install_args.release
  if install_args.ngc == True:
    release_full_name = "nvcr.io/hpc/parabricks:" + install_args.release
    run_and_return(["docker", "pull", release_full_name], "Cannot download Parabricks docker image.", False, True)
  else:
    run_and_return(["docker", "login", "registry.gitlab.com", "-u", "pbuser", "-p", install_args.access_token], "Cannot contact Parabricks registry.")
    run_and_return(["docker", "pull", release_full_name], "Cannot download Parabricks docker image.", False, True)
    run_and_return(["docker", "logout", "registry.gitlab.com"], "Error logging out of Parabricks registry.")

  print("\nInstalling image\n")
  run_and_return(["docker", "tag", release_full_name, image_full_name], "Could not build Parabricks image")

  if run_and_return(["docker", "inspect", "--type=image", image_full_name], "Image did not install correctly") == 0:
    run_and_return(["docker", "rmi", release_full_name], "Removing base image was unsuccessful")
    print("Image Installation successful.\n")
  os.chdir(currentDir)

def install_singularity_image(singularity_version):
  if "2.x" in singularity_version:
    install_singularity_image_v2()
  else:
    install_singularity_image_v3()

def install_singularity_image_v3():
  os.chdir(install_args.install_location)
  image_full_name = "parabricks-release-" + install_args.release + ".sif"
  newEnviron = os.environ.copy()
  if install_args.ngc == False:
    newEnviron["SINGULARITY_DOCKER_USERNAME"] = "pbuser"
    newEnviron["SINGULARITY_DOCKER_PASSWORD"] = install_args.access_token

  with open("pb.def", "w") as singularity_definition_file:
    singularity_definition_file.write("Bootstrap: docker\n")
    if install_args.ngc == True:
      singularity_definition_file.write("From: hpc/parabricks" + ":" + install_args.release + "\n")
      singularity_definition_file.write("Registry: nvcr.io\n\n")
    else:
      singularity_definition_file.write("From: pbuser/release/" + install_args.arch + ":" + install_args.release + "\n")
      singularity_definition_file.write("Registry: registry.gitlab.com\n\n")
    singularity_definition_file.write("%post\n")
    singularity_definition_file.write("  chmod 777 /parabricks\n")
  run_and_return(["singularity", "build", image_full_name, "pb.def"], "Could not download singularity image", False, True, newEnviron)
  os.remove("pb.def")
  os.chdir(currentDir)

#def install_singularity_image_v3():
#  os.chdir(install_args.install_location)
#  print("\nDownloading image\n")
#  image_full_name = "parabricks-release-" + install_args.release + ".sif"
#  release_full_name = "registry.gitlab.com/pbuser/release/" + install_args.arch + ":" + install_args.release
#
#  if install_args.ngc == True:
#    release_full_name = "nvcr.io/hpc/parabricks:" + install_args.release
#    run_and_return(["singularity", "pull", "docker://" + release_full_name], "Could not download singularity image", False, True, newEnviron)
#  else:
#    newEnviron = os.environ.copy()
#    newEnviron["SINGULARITY_DOCKER_USERNAME"] = "pbuser"
#    newEnviron["SINGULARITY_DOCKER_PASSWORD"] = install_args.access_token
#    run_and_return(["singularity", "pull", "docker://" + release_full_name], "Could not download singularity image", False, True, newEnviron)
#  run_and_return(["mv", install_args.arch + "_" + install_args.release + ".sif", image_full_name], "Could not copy singularity image", False, True)
#
#  print("\nInstalling image\n")
#  #run_and_return(["singularity", "image.create", "pb-overlay.img"], "Could not build Parabricks image", False, True)
#  run_and_return(["dd", "if=/dev/zero", "of=pb-overlay.img", "bs=1M", "count=256"], "Could not create overlay file", False, False)
#  run_and_return(["mkfs.ext3", "pb-overlay.img"], "Could not create ext3 overlay filesystem", False, False)
#  run_and_return(["chmod", "777", "pb-overlay.img"], "Could not fix permissions", False, False)
#  os.chdir(currentDir)

def install_singularity_image_v2():
  os.chdir(install_args.install_location)
  print("\nDownloading image\n")
  image_full_name = "parabricks-release-" + install_args.release + ".simg"
  release_full_name = "registry.gitlab.com/pbuser/release/" + install_args.arch + ":" + install_args.release

  if install_args.ngc == True:
    release_full_name = "nvcr.io/hpc/parabricks:" + install_args.release
    run_and_return(["singularity", "pull", "docker://" + release_full_name], "Could not download singularity image", False, True, newEnviron)
  else:
    newEnviron = os.environ.copy()
    newEnviron["SINGULARITY_DOCKER_USERNAME"] = "pbuser"
    newEnviron["SINGULARITY_DOCKER_PASSWORD"] = install_args.access_token
    run_and_return(["singularity", "pull", "docker://" + release_full_name], "Could not download singularity image", False, True, newEnviron)
  run_and_return(["mv", install_args.arch + "-" + install_args.release + ".simg", image_full_name], "Could not copy singularity image", False, True)

  print("\nInstalling image\n")
  run_and_return(["singularity", "image.create", "pb-overlay.img"], "Could not build Parabricks image", False, True)
  run_and_return(["chmod", "777", "pb-overlay.img"], "Could not fix permissions", False, False)

  print("Checking if image installed successfully\n")
  if run_and_return(["singularity", "inspect", image_full_name], "Image did not install correctly") == 0:
    print("Image Installation successful.\n")
  os.chdir(currentDir)

def install_image(runCmd):
  if install_args.container == "docker":
    install_docker_image()
  else:
    install_singularity_image(runCmd)

def install_docker_scripts():
  install_folder = install_args.install_location
  image_full_name = "parabricks/release:" + install_args.release

  run_and_return(["docker", "run", "--name=raw_run", image_full_name, "version" ], "Could not initiate scripts copying. Exiting...\n", False, False)
  run_and_return(["docker", "cp", "raw_run:/parabricks/release-" + install_args.release + ".tar.gz", install_folder], "Could not properly download scripts. Exiting ...\n", False, False)
  run_and_return(["docker", "rm", "-f", "raw_run"], "Could not properly complete downloading scripts. Exiting ...\n", False, False)

  run_and_return(["tar", "-xzf", install_folder + "/release-" + install_args.release + ".tar.gz", "-C", install_folder], "Could not properly untar release scripts")
  copy_tree(install_folder + "/release-" + install_args.release, install_folder)
  os.remove(install_folder + "/release-" + install_args.release + ".tar.gz")
  shutil.rmtree(install_folder + "/release-" + install_args.release)

def install_singularity_scripts(runCmd):
  install_folder = install_args.install_location
  image_full_name = "parabricks-release-" + install_args.release
  if "3.x" in runCmd:
    image_full_name = image_full_name + ".sif"
  else:
    image_full_name = image_full_name + ".simg"
  run_and_return(["singularity", "build", "--sandbox", "/tmp/pb_sb_" + install_args.release, install_folder + "/" + image_full_name], "Could not initiate scripts copying", False, False)
  run_and_return(["cp", "/tmp/pb_sb_" + install_args.release + "/parabricks/release-" + install_args.release + ".tar.gz", install_folder], "Copying from sandbox failed", False, False)
  shutil.rmtree("/tmp/pb_sb_" + install_args.release)

  run_and_return(["tar", "-xzf", install_folder + "/release-" + install_args.release + ".tar.gz", "-C", install_folder], "Could not properly untar release scripts")
  copy_tree(install_folder + "/release-" + install_args.release, install_folder)
  os.remove(install_folder + "/release-" + install_args.release + ".tar.gz")
  shutil.rmtree(install_folder + "/release-" + install_args.release)

def install_scripts(install_folder, runCmd):
  print("Copying Scripts\n")
  if install_args.container == "docker":
    install_docker_scripts()
  else:
    install_singularity_scripts(runCmd)

  if install_args.symlink == True:
    try:
      if os.path.lexists("/usr/bin/pbrun"):
        os.unlink("/usr/bin/pbrun")
      os.symlink(install_folder + "/pbrun", "/usr/bin/pbrun")
    except OSError as exc:
      print("Could not create symlink /usr/bin/pbrun. Permission denied")

def install_parabricks(script_dir):
  runCmd = check_requirements(install_args.cpu_only)
  install_folder = install_args.install_location #Easy access the same variable
  if os.path.isfile(script_dir + "/license.bin") == False:
    print ("License file " + scipt_dir + "/license.bin" + " does not exist. Exiting...")
    InstallAbort()

  check_install_folder(install_folder)
  if os.path.abspath(script_dir + "/license.bin") != os.path.abspath(install_folder + "/license.bin"):
    shutil.copy(script_dir + "/license.bin", install_folder + "/license.bin" )

  install_image(runCmd)
  install_scripts(install_folder, runCmd)
  run_and_return([install_folder + "/pbrun", "version" ], "Could not test version. Exiting...\n", False, False)
  with open(install_folder + "/config.txt", "w") as f:
    f.write(runCmd + "\n")
    f.write(install_args.arch + "\n")
  print("Installation successful")

if __name__ == '__main__':
  currentDir = os.getcwd()
  scriptDir = os.path.dirname(os.path.realpath(__file__))
  install_args = get_install_args()

  with open("/tmp/pb_install_log_" + str(time.time()) + ".txt", "w") as log_file:
    if install_args.uninstall == True:
      uninstall_pbrun(install_args)
    else:
      GetEULAAgreement(scriptDir, install_args)
      print_selection(install_args)
      install_parabricks(scriptDir)

