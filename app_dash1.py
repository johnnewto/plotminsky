# import cProfile

from dash import Dash, html, dcc, Input, Output, Patch, callback, ALL, State, callback_context, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from pyminsky import minsky
import threading
import queue
import time
import json
import re
import os

# Enable Flask to watch config.json
extra_files = ['config.json']

# Load configuration from JSON file
def load_config():
    with open('config.json', 'r') as f:
        config = json.load(f)
        return config['figs'], config['sliders']

# Initial load of configuration
figs, sliders = load_config()

# make a list of all the traces
traces = []
for fig_config in figs:
    sublist = []
    for trace in fig_config["traces"]:
        trace["id"] = trace["variable"].replace(':', '').replace('{', '').replace('}', '').replace('^', '').replace('%', '')
        sublist.append(trace)
    traces.append(sublist)

print([(trace["name"], trace["id"]) for sublist in traces for trace in sublist])


def translate_minsky_var(var_name, to_latex=True):
    """
    Translate Minsky variable names between HTML and LaTeX formats.
    
    Args:
        var_name (str): The variable name to translate
        to_latex (bool): If True, convert from HTML to LaTeX format. If False, convert from LaTeX to HTML.
    
    Returns:
        str: The translated variable name
    """
    if to_latex:
        # Convert HTML format to LaTeX
        var_name = var_name.replace('<sub>', '_{').replace('</sub>', '}')
        var_name = var_name.replace('<sup>', '^{').replace('</sup>', '}')
    else:
        # Convert LaTeX format to HTML
        # Handle subscripts
        var_name = re.sub(r'_{([^}]+)}', r'<sub>\1</sub>', var_name)
        # Handle superscripts
        var_name = re.sub(r'\^{([^}]+)}', r'<sup>\1</sup>', var_name)
    return var_name

def get_minsky_var(var_name):
    """
    Get a Minsky variable value, handling both HTML and LaTeX formats.
    
    Args:
        var_name (str): The variable name in either HTML or LaTeX format
    
    Returns:
        The value of the Minsky variable
    """
    html_name = translate_minsky_var(var_name, to_latex=False)
    return minsky.variableValues[html_name].value()

def set_minsky_var(var_name, value):
    """
    Set a Minsky variable value, handling both HTML and LaTeX formats.
    
    Args:
        var_name (str): The variable name in either HTML or LaTeX format
        value: The value to set
    """
    html_name = translate_minsky_var(var_name, to_latex=False)
    minsky.variableValues[html_name].setValue(value)


# Thread-safe queue for simulation results with max size of 5
simulation_queue = queue.Queue(maxsize=5)

# Add at the top of the file with other global variables
policy_change_times = []

class SimulationThread(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True  # Thread will exit when main program exits
        self.running = True
        self.steps_per_update = 10

    def get_queue_length(self):
        return simulation_queue.qsize()

    def get_results(self, flatten=False):
        # Get current values
        sim_time = minsky.t()
        results = []
        results.append([sim_time])
        
        # Iterate through all traces in figs to get values
        for fig_config in figs:
            graphs = []
            for trace in fig_config["traces"]:
                var_name = trace["variable"]
                graphs.append(get_minsky_var(var_name) * trace["multiplier"])
            results.append(graphs)
        
        return results if not flatten else self.flatten(results)


    def get_results_dict(self):
        results = self.get_results()
        return {
            'time': results[0],
            **{trace['id']: results[i+1][j] for i, trace in enumerate(traces) for j, _ in enumerate(trace['traces'])}
        }
    
    def get_trace_names(self, flatten=False):
        return [trace['name'] for trace in traces] if not flatten else [trace['name'] for sublist in traces for trace in sublist]
    
    def get_trace_ids(self):
        return [trace['id'] for trace in traces]
    
    def flatten(self, matrix):
        flat_list = []
        for row in matrix:
            flat_list += row
        return flat_list


    def run(self):
        while self.running:
            if minsky.running():
                # Run simulation steps
                for _ in range(self.steps_per_update):
                    minsky.step()
                
                # Get current values
                results = self.get_results()
                simulation_queue.put(results)
            
            time.sleep(0.01)  # Small sleep to prevent CPU hogging

# Create and start simulation thread
sim_thread = SimulationThread()
sim_thread.start()

app = Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.SPACELAB, 
        dbc.icons.FONT_AWESOME,
        '/assets/custom.css'
    ]
)

# Initialize the Minsky model
model_file = "BOMDwithGovernmentLive.mky"
minsky.load(model_file)
minsky.reset()
minsky.order(4)  # 4th order Runge-Kutta
minsky.implicit(0)  # Explicit integration
minsky.running(True)  # Start in running state

def show_minsky_variables():
    # print(minsky.variableValues.keys())
    stocks = []
    flows = []
    parameters = []

    for variable_name in minsky.variableValues.keys():
        var = minsky.variableValues[variable_name]
        if var.type() == 'flow':
            flows.append(variable_name)
        elif var.type() == 'stock':
            stocks.append(variable_name)
        else:
            parameters.append(variable_name)
    return flows, stocks, parameters



def create_figures():
    # Create initial figures for all charts with proper layout
    figures = {}
    
    for fig_config in figs:
        fig = go.Figure()
        
        # Add traces
        for trace in fig_config["traces"]:
            fig.add_trace(go.Scatter(x=[], y=[], name=r'$' + trace["name"] + '$'))
        
        # Update layout
        fig.update_layout(
            title=fig_config["title"],
            xaxis_title=fig_config["xaxis_title"],
            yaxis_title=fig_config["yaxis_title"],
            showlegend=True,
            height=350,  # Reduced height
            margin=dict(
                t=25,    # Reduced top margin
                b=20,    # Reduced bottom margin
                l=40,    # Left margin
                r=10     # Right margin
            ),
            legend=dict(
                orientation="v",  # Vertical legend
                yanchor="top",
                y=1,
                xanchor="left",
                x=0,
                bgcolor="rgba(255, 255, 255, 0.5)",  # Semi-transparent white
                bordercolor="rgba(0, 0, 0, 0.2)",    # Light gray border
                borderwidth=1,
                font=dict(size=10)  # Smaller font size
            ),
            template='plotly'
        )
        
        # Store figure with its graph_id
        figures[fig_config["graph_id"]] = fig
    
    return figures

figures = create_figures()


# Markdown text components
simulation_text = dcc.Markdown(
    """
    > This simulation shows the dynamic behavior of key economic indicators over time.
    > The model demonstrates how GDP, debt levels, money supply, and interest payments
    > interact in a Minsky-style economic system.
    """
)

learn_text = dcc.Markdown(
    """
    The Minsky model demonstrates how financial instability can emerge from seemingly stable conditions.
    Key concepts shown in this simulation:

    - **GDP Growth**: Shows overall economic activity
    - **Debt Levels**: Tracks both government and private sector debt as percentage of GDP
    - **Money Supply**: Shows the flow of money through different sectors
    - **Interest Payments**: Demonstrates the burden of debt service on the economy

    The simulation updates every 10 steps to show the evolution of these indicators over time.
    """
)

# Create cards for different sections
simulation_card = dbc.Card(simulation_text, className="mt-2")
learn_card = dbc.Card(
    [
        dbc.CardHeader("Understanding the Minsky Model"),
        dbc.CardBody(learn_text),
    ],
    className="mt-4",
)

# Create tabs
tabs = dbc.Tabs(
    [
        dbc.Tab(learn_card, tab_id="tab1", label="Learn"),
        dbc.Tab(
            [
                simulation_card,
                html.Div([
                    html.Div([
                        html.Button(
                            html.I(className="fas fa-play"),
                            id="play-pause-button",
                            className="btn btn-primary me-2"
                        ),
                        html.Button(
                            html.I(className="fas fa-redo"),
                            id="rerun-button",
                            className="btn btn-warning"
                        ),
                    ], className="mb-3"),
                    *[
                        html.Div([
                            html.Label(slider["label"], className="mt-3"),
                            dcc.Slider(
                                id=slider["id"],
                                min=slider["min"],
                                max=slider["max"],
                                step=slider["step"],
                                value=get_minsky_var(slider["minsky_var"]) * slider["multiplier"] if slider["minsky_var"] else slider["value"],
                                marks=slider["marks"],
                                tooltip={"placement": "bottom", "always_visible": True}
                            ),
                        ]) for slider in sliders
                    ]
                ]),
            ],
            tab_id="tab-2",
            label="Simulate",
            className="pb-4",
        ),
    ],
    id="tabs",
    active_tab="tab-2",
    className="mt-2",
)

# Main layout
app.layout = dbc.Container(
    [
        dbc.Row(
            dbc.Col(
                html.H2(
                    "Minsky Economic Model Simulation",
                    className="text-center bg-primary text-white p-2",
                ),
            )
        ),
        dbc.Row(
            [
                html.Div(
                    [
                        html.Button(
                            html.I(className="fas fa-chevron-left"),
                            id="toggle-sidebar",
                            className="btn btn-primary",
                            style={
                                "width": "40px", 
                                "height": "40px",
                                "position": "absolute",
                                "left": "0px",
                                "top": "0px",
                                "z-index": "1000"
                            }
                        ),
                        dbc.Col(
                            [
                                tabs,
                            ],
                            id="sidebar-column",
                            width={"size": 4, "order": 1},
                            # xs=12,  # Full width on extra small screens
                            className="mt-4 border",
                            style={
                                "maxHeight": "calc(100vh - 100px)",  # Set max height to viewport height minus some space for header
                                "overflowY": "auto",  # Add vertical scrollbar when needed
                                "padding": "10px"  # Add some padding
                            }
                        ),
                        dbc.Col(
                            [
                                dbc.Tabs(
                                    [
                                        dbc.Tab(
                                            [
                                                html.Div([
                                                    dcc.Graph(figure=list(figures.items())[0][1], id=list(figures.items())[0][0], mathjax=True),
                                                    dcc.Graph(figure=list(figures.items())[1][1], id=list(figures.items())[1][0], mathjax=True),
                                                ], style={'width': '50%', 'display': 'inline-block'}),
                                                html.Div([
                                                    dcc.Graph(figure=list(figures.items())[2][1], id=list(figures.items())[2][0], mathjax=True),
                                                    dcc.Graph(figure=list(figures.items())[3][1], id=list(figures.items())[3][0], mathjax=True),
                                                ], style={'width': '50%', 'display': 'inline-block'}),
                                            ],
                                            label="All Plots",
                                            tab_id="tab-plots-all",
                                        ),

                                        dbc.Tab(
                                            [
                                                dbc.Table(
                                                    [
                                                        html.Thead(
                                                            html.Tr([
                                                                html.Th("Metric"),
                                                                html.Th("Latest Value"),
                                                            ])
                                                        ),
                                                        html.Tbody([
                                                            html.Tr([
                                                                html.Td("Simulation Time"),
                                                                html.Td(id="latest-time"),
                                                            ]),
                                                            *[html.Tr([
                                                                html.Td(trace["name"]),
                                                                html.Td(id=f"latest-{trace['id']}"),
                                                            ]) for sublist in traces for trace in sublist]
                                                        ])
                                                    ],
                                                    bordered=True,
                                                    hover=True,
                                                    responsive=True,
                                                    striped=True,
                                                ),
                                            ],
                                            label="Latest Values",
                                            tab_id="tab-values",
                                        ),
                                    ],
                                    id="plots-tabs",
                                    active_tab="tab-plots-all",
                                ),
                            ],
                            id="main-content",
                            width={"size": 8, "order": 2},
                            # xs=12,  # Full width on extra small screens
                            className="pt-4"
                        ),
                    ],
                    className="resizable-container",
                    style={
                        'display': 'flex',
                        'position': 'relative',
                    }
                ),
            ],
            className="ms-1"
        ),
        dcc.Store(id='session-state', storage_type='session', data={'do_clear_figs': True, 'is_running': True}),
        dcc.Interval(
            id='interval-component',
            interval=500,  # in milliseconds
            n_intervals=0,
            disabled=False
        ),
        dcc.Interval(
            id='values-interval-component',
            interval=1000,  # 1 second in milliseconds
            n_intervals=0,
            disabled=False
        )
    ],
    fluid=True
)

@callback(
    [Output("play-pause-button", "children"),
     Output("play-pause-button", "className"),
     Output("rerun-button", "disabled")],
    Input("session-state", "data"),
    prevent_initial_call=False
)
def set_initial_button_state(session_state):
    if session_state.get('is_running', True):
        return html.I(className="fas fa-pause"), "btn btn-primary me-2", True
    else:
        return html.I(className="fas fa-play"), "btn btn-primary me-2", False

@callback(
    [Output('session-state', 'data', allow_duplicate=True),
     Output('interval-component', 'disabled', allow_duplicate=True),
     Output("play-pause-button", "children", allow_duplicate=True),
     Output("play-pause-button", "className", allow_duplicate=True),
     Output("rerun-button", "disabled", allow_duplicate=True)],
    [Input("rerun-button", "n_clicks"),
     Input("play-pause-button", "n_clicks")],
    [State('session-state', 'data'),
     State("play-pause-button", "children")],
    prevent_initial_call=True
)
def handle_control(n_clicks_rerun, n_clicks_play, session_state, current_icon):
    ctx = callback_context
    if not ctx.triggered:
        return no_update, no_update, no_update, no_update, no_update
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    print(f"Control triggered by {trigger_id}", session_state)
    
    if trigger_id == "rerun-button":
        print("Rerun clicked")

        # make a list current values of the policy variables
        policy_vars = []
        for slider in sliders:
            if slider['minsky_var'] is not None:
                policy_vars.append((slider['minsky_var'], get_minsky_var(slider['minsky_var'])))

        minsky.reset()
        minsky.running(False)
        # set the minsky variables to the current values
        print("Setting Policy Variables: ")
        for var in policy_vars:
            set_minsky_var(var[0], var[1])  

        # Clear the simulation queue
        while not simulation_queue.empty():
            try:
                simulation_queue.get_nowait()
            except queue.Empty:
                break

        session_state['is_running'] = False
        session_state['do_clear_figs'] = True
        session_state['policy_change_times'] = []
        print("Setting: ", session_state)
        return session_state, False, html.I(className="fas fa-play"), "btn btn-primary me-2", False
    
    elif trigger_id == "play-pause-button":
        print("Play/Pause clicked")
        if current_icon is None or "fa-pause" in str(current_icon):
            minsky.running(False)
            session_state['is_running'] = False
            return session_state, True, html.I(className="fas fa-play"), "btn btn-primary me-2", False
        else:
            minsky.running(True)
            session_state['is_running'] = True
            session_state['do_clear_figs'] = False
            return session_state, False, html.I(className="fas fa-pause"), "btn btn-primary me-2", True




@callback(
    [Output(fig_config["graph_id"], 'figure', allow_duplicate=True) for fig_config in figs] + 
    [Output('interval-component', 'disabled', allow_duplicate=True)],
    [Input("interval-component", "n_intervals")],
    [State('session-state', 'data')],
    prevent_initial_call=True,
)
def update_graphs(n_intervals, session_state):
    ctx = callback_context
    if not ctx.triggered:
        print('ctx not triggered')
        return [no_update for _ in figs] + [False]    

    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # Handle clearing
    if session_state.get('do_clear_figs', True):
        print("Clearing figures", session_state)
        session_state['do_clear_figs'] = False
        patches = []
        for fig_config in figs:
            patched_fig = Patch()
            for i in range(len(fig_config["traces"])):
                patched_fig["data"][i]["x"] = []
                patched_fig["data"][i]["y"] = []
            patches.append(patched_fig)

        return patches + [True]

    
    # Check if model is running
    if minsky.running() and session_state.get('is_running', True):
        results = None
        try:
            # Get latest simulation results from queue
            while not simulation_queue.empty():
                results = simulation_queue.get_nowait()
            
            if results:
                # print("Results: ", results)
                # Create patches for all figures
                patches = []
                sim_time = results[0][0]

                for i, graph in enumerate(results[1:]):
                    patched_fig = Patch()
                    for j, value in enumerate(graph):
                        patched_fig["data"][j]["x"].append(sim_time)
                        patched_fig["data"][j]["y"].append(value)
                    patches.append(patched_fig)

                return patches + [False]
            else:
                print("No results in queue")
                return [no_update for _ in figs] + [False]
        except queue.Empty:
            print("No results in queue")
            pass
    print('paused')
    return [no_update for _ in figs] + [True]


## Slider callbacks

@callback(
    Output("interval-component", "interval"),
    Input("update-interval", "value")
)
def update_interval(value):
    return value

# Generate callbacks for each Minsky variable slider
for slider in sliders:
    if slider['minsky_var'] is not None:
        callback(
            Output(slider['id'], "value"),
            Input(slider['id'], "value")
        )(lambda value, slider=slider: (
            set_minsky_var(slider['minsky_var'], value / (100 if slider['units'] == "%" else 1)) if value is not None else None,
            value
        )[1])

@callback(
    [Output("sidebar-column", "style"),        # First return value: {"display": "block"}
     Output("toggle-sidebar", "children"),      # Second return value: html.I(className="fas fa-chevron-left")
     Output("sidebar-column", "width"),         # Third return value: 5
     Output("main-content", "width")],          # Fourth return value: 7
    Input("toggle-sidebar", "n_clicks"),
    State("sidebar-column", "style"),
    prevent_initial_call=True
)
def toggle_sidebar(n_clicks, current_style):
    if current_style is None:
        current_style = {"display": "block"}
    
    if current_style.get("display") == "none":
        return {"display": "block"}, html.I(className="fas fa-chevron-left"), 4, 8
    else:
        return {"display": "none"}, html.I(className="fas fa-chevron-right"), 0, 12



@callback(
    [Output("latest-time", "children"),
     *[Output(f"latest-{trace['id']}", "children") for sublist in traces for trace in sublist]],
    [Input("values-interval-component", "n_intervals")],
    prevent_initial_call=True,
)
def update_latest_values(n_intervals):
    results = sim_thread.get_results(flatten=True)
    # names = sim_thread.get_trace_names(flatten=True)
    txt = []
    for i, value in enumerate(results):
        # print(names[i], value)
        txt.append(f"{value:.2f}")
    return txt

    # # for debugging
    # int_rate = minsky.variableValues[":Interest_{Rate}"].value()
    # lend_frac = minsky.variableValues[":Lend_{Frac}"].value()
    # spend_frac = minsky.variableValues[":Spend_{Frac}"].value()
    # print("Interest Rate: ", int_rate, "Lend Fraction: ", lend_frac, "Spend Fraction: ", spend_frac)
    # return sim_time, gdp, gov_debt, priv_debt, money, savers, borrowers, banks, gov_int, priv_int, gdp_inc


@app.callback(
    [Output(fig_config["graph_id"], 'figure', allow_duplicate=True) for fig_config in figs] + 
    [Output('session-state', 'data', allow_duplicate=True)],
    [Input(slider["id"], "value") for slider in sliders if slider["minsky_var"] is not None],
    [Input("rerun-button", "n_clicks")],
    [State('session-state', 'data')],
    prevent_initial_call=True
)
def update_policy_lines(*args):
    # Get the triggering input
    ctx = callback_context
    if not ctx.triggered:
        return no_update, no_update, no_update, no_update, session_state
    
    # Get slider values and session state
    slider_values = args[:-2]  # All args except last two (rerun_n_clicks and session_state)
    rerun_n_clicks = args[-2]
    session_state = args[-1]
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    print("Trigger ID: update_policy_lines: ", trigger_id)
    
    # Clear policy change times if simulation is reset
    if trigger_id == 'rerun-button' :
        print("Clearing policy change times", session_state, "rerun_n_clicks", rerun_n_clicks)
        session_state['policy_change_times'] = []
        patched_policy = Patch()
        patched_policy['layout']['shapes'] = []
        return patched_policy, patched_policy, patched_policy, patched_policy,  session_state
    
    # Create patches for all figures
    patched = Patch()

    
    # Get current simulation time
    current_time = minsky.t()
    
    # Add shapes based on trigger type
    shapes = []
    
    # Add policy change line if triggered by slider ( ie not session state)
    if trigger_id != 'session-state':
        # Add current time to history
        if 'policy_change_times' not in session_state:
            session_state['policy_change_times'] = []
        session_state['policy_change_times'].append(current_time)
    
    # Always add lines for all policy changes, regardless of trigger
    if 'policy_change_times' in session_state:
        print("Adding lines for all policy changes")
        for time in session_state['policy_change_times']:
            shapes.append({
                'type': 'line',
                'x0': time,
                'x1': time,
                'y0': 0,
                'y1': 1,
                'yref': 'paper',
                'line': {'color': 'gray', 'dash': 'dot', 'width': 1}
            })
    
    # Update all figures with the shapes
    patched['layout']['shapes'] = shapes
    return [patched for _ in figs] + [session_state]


if __name__ == "__main__":
    # cProfile.run('app.run(debug=True)', 'output.prof')
    app.run(debug=True, extra_files=extra_files)