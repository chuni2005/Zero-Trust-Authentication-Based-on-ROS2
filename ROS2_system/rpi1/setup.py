#mkdir -p ~/ros2_ws/src/my_pubsub/resource
#touch ~/ros2_ws/src/my_pubsub/resource/my_pubsub

from setuptools import find_packages, setup

package_name = 'my_pubsub'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='raspberry01',
    maintainer_email='raspberry01@todo.todo',
    description='Normal ROS2 publisher node for my_pubsub package',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'publisher = my_pubsub.publisher:main',
        #    'subscriber = my_pubsub.subscriber:main',
        ],
    },
)