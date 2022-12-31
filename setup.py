import setuptools

with open('README.md', 'r') as fh:
    long_description = fh.read()

setuptools.setup(
    name='pyjs8call',
    version='0.1.1',
    author='Simply Equipped LLC',
    author_email='howard@simplyequipped.com',
    description='Python interface for JS8Call API',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/simplyequipped/pyjs8call',
    packages=setuptools.find_packages(),
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: POSIX :: Linux'
    ],
    python_requires='>=3.6'
)
