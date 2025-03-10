"""
This file stores the parameters for the experimental setups
It contains information that should be available both to TO_main.py 
and to robot_control.py. By defining them here and then importing
this file where needed, we avoid duplicating things.

It acts as a server to allow quick update of various parameters.
"""

import rospy

from dynamic_reconfigure.server import Server
from biomechanical_safe_deflection.cfg import ParameterUpdateConfig

import os
import numpy as np
from scipy.spatial.transform import Rotation as R

# import parser
import argparse

def callback(config, level):
    """
    This callback sets parameters of the ROS Parameter Server, so that
    the modifications are accessible to other nodes too. This is done specifically
    with the return command. Before, we can print something to make the user happy!
    """
    # rospy.loginfo("""l_arm: {l_arm},
    #               p_gh:[{p_gh_in_base_x}, {p_gh_in_base_y}, {p_gh_in_base_z}],
    #               high cart stiff:[{ee_trans_stiff_h}, {ee_trans_stiff_h}, {ee_trans_stiff_h}, {ee_rot_stiff_xy_h}, {ee_rot_stiff_xy_h}, {ee_rot_stiff_z_h}],
    #               low cart stiff:[{ee_trans_stiff_l}, {ee_trans_stiff_l}, {ee_trans_stiff_l}, {ee_rot_stiff_xy_l}, {ee_rot_stiff_xy_l}, {ee_rot_stiff_z_l}],
    #               increase damping by x {damp_ratio},
    #               mode:{interaction_mode}, 
    #               task:{task}, 
    #               execute:{execute_program}""".format(**config))
    return config

if __name__ == "__main__":
    
    # initialize the pu (parameter updater)
    rospy.init_node("pu", anonymous = False)

    # check if we are going to allow online parameter updates or not
    parser = argparse.ArgumentParser(description="Script that initializes ROS parameters")
    parser.add_argument("--update", type=str, help="Allow online parameter updates")
    args, unknown = parser.parse_known_args()
    
    if args.update:
        update = args.update
        rospy.loginfo(f"ParamUpdater: running with command-line argument: updatable={update }")
    else:
        # Fallback to ROS parameter if not provided as an argument
        update = rospy.get_param("~update", "false")
        rospy.loginfo(f"ParamUpdater: running with ROS parameter: updatable={update}")
    
    # First, let's set all of the parameters that we will need. Only some of them are defined as
    # modifiable by the BSDConfig.

    # set the frequency to check for new message and execute loops
    loop_frequency = 20    # [Hz]

    # select here with which setup/subject we are working
    subject = 'subject1'       # list of available subjects: subject1, subject2, subject3

    setup = 'newLab_facingRobot'        # list of setups: 'OldLab' (configuration that the robot had before 12/12/2023)

    # physical parameters related to the experimental setup (they could be different every time)
    #   * l_arm:  (subject-dependent) length of the segment between the glenohumeral joint center 
    #             and the elbow tip, when the elbow of the subject is bent at 90 degrees 
    #   * l_brace: (fixed) length of the segment between the elbow tip and the robot end-effector, when
    #              the subject is wearing the brace - it is the thickness of the brace along the arm direction 
    #   * base_R_shoulder: rotation that expresses the orientation of the human shoulder frame in the 
    #                      base frame of the robot  
    #   * position_gh_in_base: position of the center of the shoulder frame (GH joint) in the base frame [m]


    if subject=='subject1':
        l_arm = 0.32            # length of the subject's right arm, from the center of the glenohumeral (GH) joint to the elbow [m]
    elif subject == 'subject2':
        l_arm = 0.35
    elif subject == 'subject3':
        l_arm = 0.3


    if setup=='newLab_facingRobot':                  
        # This is the setup used now that the KUKA7 is mounted on the table
        rot_sh_in_base = np.array([np.pi/2, 0, 0])      # intrinsic series of rotations around the x-y-z axis of the robot base 
                                                        # to align it with shoulder frame [rad]
        # if the person is facing the robot, looking along the +X direction of the base: np.array([np.pi/2, 0, 0]) 

        base_R_shoulder = R.from_euler('x', rot_sh_in_base[0]) * R.from_euler('y', rot_sh_in_base[1]) * R.from_euler('z', rot_sh_in_base[2])

        # define the initial position of the glenohumeral joint in the robot's base
        # (this is used so that the robot knows where to go as a starting point)
        if subject == 'subject1':
            position_gh_in_base = np.array([-0.9, 0, 0.62])
        elif subject == 'subject2':
            position_gh_in_base = np.array([-0.9, 0, 0.68])
        elif subject == 'subject3':
            position_gh_in_base = np.array([-0.85, 0, 0.57])

        ar_offset = 0

    if setup=='OldLab':                  
        # This is the setup used before the lab was moved
        rot_sh_in_base = np.pi/2    # rotation around the x axis of the robot base to align it with shoulder frame [rad]
        base_R_shoulder = R.from_euler('x', rot_sh_in_base, degrees=False)

        position_gh_in_base = np.array([-0.2, 0.8, 0.6]) # position of the center of the shoulder frame (GH joint) in the base frame [m]

    # definition of parameters for strain map and ellipses
    x0 = 40                 # PE center in degrees
    y0 = 90                 # SE center in degrees
    sigma_x = 35            # standard deviation along PE in degrees
    sigma_y = 25            # standard deviation along SE in degrees
    amplitude = 5           # max strain at the top
    strain_offset = 0       # constant offset to elevate strain-map
    strain_threshold = 1.5  # strain threshold to define risky zones

    # initial state (referred explicitly to the position of the patient's GH joint) 
    # Therapy will start in this position - used to build the NLP structure, and to command first position of the robot
    # x = [pe, pe_dot, se, se_dot, ar, ar_dot], but note that ar and ar_dot are not tracked

    x_0 = np.deg2rad(np.array([80, 0, 60, 0, 0, 0]))
    # x_0 = np.deg2rad(np.array([55, -10, 100, 0, 0, 0]))
    # print("INITIAL POSITION IS UNSAFE!!!")

    # estimation of velocities in human coordinates
    speed_estimate = True

    # specify the stiffness and damping for the cartesian impedance controller implemented on the robot
    # we do this both for the nullspace controlling the elbow (ns_elb) and for the end effector
    ns_elb_stiffness = np.array([10, 10, 10])
    ns_elb_damping = 2*np.sqrt(ns_elb_stiffness)

    # control parameters for when the robot needs to deflect the user (high stiffness, damping will be 2*srqt(...))
    ee_trans_stiff_h = 400
    ee_rot_stiff_xy_h = 20
    ee_rot_stiff_z_h = 20 

    # control parameters for when the user moves around safely (low stiffness, damping will be 2*srqt(...))
    ee_trans_stiff_l = 20
    ee_rot_stiff_xy_l = 5
    ee_rot_stiff_z_l = 20 
    # ratio to modify damping wrt critical one (for low stiffness)
    damp_ratio = 4

    # option to change these only in simulation
    ns_elb_stiffness_sim = ns_elb_stiffness
    ns_elb_damping_sim = ns_elb_damping

    # -------------------------------------------------------------------------------
    # experimental parameters used by both the TO and the robot control modules
    l_brace = 0.02          # thickness of the brace [m]

    position_gh_in_ee = np.array([0, 0, l_arm+l_brace])     # position of the center of the shoulder frame (GH joint) in the EE frame [m]

    dist_shoulder_ee = np.array([0, -(l_arm+l_brace), 0])   # evaluate the distance between GH center and robot ee, in shoulder frame 
                                                            # (once the subject is wearing the brace)
    elb_R_ee = R.from_euler('x', -np.pi/2, degrees=False)   # rotation matrix expressing the orientation of the ee in the elbow frame

    # now let's set all of the relevant parameters
    # the problem is that we need to use very simple data structures here...
    rospy.set_param('/pu/p_gh_in_base_x', float(position_gh_in_base[0]))
    rospy.set_param('/pu/p_gh_in_base_y', float(position_gh_in_base[1]))
    rospy.set_param('/pu/p_gh_in_base_z', float(position_gh_in_base[2]))
    rospy.set_param('/pu/p_gh_in_ee', position_gh_in_ee.tolist())
    rospy.set_param('/pu/base_R_shoulder', base_R_shoulder.as_matrix().tolist())
    rospy.set_param('/pu/l_arm', l_arm)
    rospy.set_param('/pu/l_brace', l_brace)
    rospy.set_param('/pu/d_gh_ee_in_shoulder', dist_shoulder_ee.tolist())
    rospy.set_param('/pu/elb_R_ee', elb_R_ee.as_matrix().tolist())
    rospy.set_param('/pu/estimate_gh_position', True)
    rospy.set_param('/pu/loop_frequency', loop_frequency)
    rospy.set_param('/pu/ar_offset', ar_offset)
    rospy.set_param('/pu/x_0', x_0.tolist())
    rospy.set_param('/pu/speed_estimate', speed_estimate)
    rospy.set_param('/pu/ns_elb_stiffness', ns_elb_stiffness.tolist())
    rospy.set_param('/pu/ns_elb_damping', ns_elb_damping.tolist())

    # define the parameters for the CIC
    # high stiffness (for when the robot needs to actively deflect the subject)
    rospy.set_param('/pu/ee_trans_stiff_h', ee_trans_stiff_h)
    rospy.set_param('/pu/ee_rot_stiff_xy_h', ee_rot_stiff_xy_h)
    rospy.set_param('/pu/ee_rot_stiff_z_h', ee_rot_stiff_z_h)
    # low stiffness (for when the subject moves around undisturbed)
    rospy.set_param('/pu/ee_trans_stiff_l', ee_trans_stiff_l)
    rospy.set_param('/pu/ee_rot_stiff_xy_l', ee_rot_stiff_xy_l)
    rospy.set_param('/pu/ee_rot_stiff_z_l', ee_rot_stiff_z_l)
    # ratio to increase damping in certain directions
    rospy.set_param('/pu/damp_ratio', damp_ratio)

    # define the parameters for the interaction mode
    rospy.set_param('/pu/interaction_mode', 0)

    # define the parameter for the task (0 means just wait)
    rospy.set_param('/pu/task', 0)

    # define parameters related to the predictive deflection
    rospy.set_param('/pu/time_horizon', 1)

    # define parameter for terminating execution
    rospy.set_param('/pu/execute_program', True)

    # define parameters for the ellipse definition
    rospy.set_param('/pu/x0', x0)
    rospy.set_param('/pu/y0', y0)
    rospy.set_param('/pu/sigma_x', sigma_x)
    rospy.set_param('/pu/sigma_y', sigma_y)
    rospy.set_param('/pu/amplitude', amplitude)
    rospy.set_param('/pu/strain_offset', strain_offset)
    rospy.set_param('/pu/strain_threshold', strain_threshold)

    # -------------------------------------------------------------------------------
    # names of the ROS topics on which the shared communication between biomechanical-based optimization 
    # and robot control will happen
    # we also use ros parameters here
    rospy.set_param('/rostopic/estimated_shoulder_pose', 'estimated_shoulder_pose')
    rospy.set_param('/rostopic/cartesian_init_pose', 'cartesian_init_pose')
    rospy.set_param('/rostopic/cartesian_ref_ee', 'cartesian_ref_ee')
    rospy.set_param('/rostopic/request_reference', 'request_reference')
    rospy.set_param('/rostopic/optimization_output', 'optimization_output')
    rospy.set_param('/rostopic/z_level', 'uncompensated_z_ref')

    print("Parameters have been initialized correctly")

    if update == 'false':
        print("Cannot modify them during execution")
    else:
        srv = Server(ParameterUpdateConfig, callback)
        rospy.spin()
