<p align="center">
  <img alt="Cairo DAP" src="https://raw.githubusercontent.com/fracek/cairo-dap/main/.images/cairo-dap-logo.png">
</p>

# Cairo Debugger Adapter Protocol Server

## Development

To hack on `cairo-dap` you need to install [Starkware's Cairo](https://github.com/starkware-libs/cairo-lang) and
then run the following command:

```shell
python setup.py develop
```

## Running

* Compile your program with `cairo-compile`

```shell
cairo-compile my-program.cairo --output my-program.json
```

* Start the DAP server

```shell
cairo-dap --program my-program.json --layout=small
```

You then need to connect your editor to the DAP server which is listening
on port 9999. If you're using VS Code, you can add the following launch
configuration:

```json
{
  "type": "python",
  "request": "attach",
  "name": "Cairo",
  "internalConsoleOptions": "openOnSessionStart",
  "connect": {
    "host": "localhost",
    "port": 9999                            
  }
}
```

### Setting breakpoints in VS Code

You need to enable breakpoints everywhere by going to *File -> Settings -> Debug*
and changing `debug.allowBreakpointsEverywhere` to `true`.

## License

    Copyright 2021 Francesco Ceccon
    
    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at
    
        http://www.apache.org/licenses/LICENSE-2.0
    
    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
