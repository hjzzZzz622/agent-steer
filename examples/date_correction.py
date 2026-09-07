"""Deterministic simulated tool boundary; no model credentials required."""
from agent_steer import InMemorySteeringQueue
from agent_steer.adapters.base import apply_pending


def main():
    queue = InMemorySteeringQueue()
    state = {'run_id': 'daily-report', 'date': '0907', 'steps': ['plan']}
    data = {'0906': [{'revenue': 120}]}
    print(f"run={state['run_id']}: query {state['date']} -> {data.get(state['date'], [])}")
    queue.submit(state['run_id'], '0907 数据尚未落库，请查询 0906')

    def apply(message):
        print(f'steer: {message.text}')
        # A deterministic host policy for this demo, not general text parsing.
        if message.text != '0907 数据尚未落库，请查询 0906':
            raise ValueError('unsupported demo guidance')
        state['date'] = '0906'

    apply_pending(queue, state['run_id'], apply)
    rows = data[state['date']]
    state['steps'].append('query')
    print(f"run={state['run_id']}: query {state['date']} -> {rows}")
    print(f"preserved progress: {state['steps']}")
    return state, rows


if __name__ == '__main__':
    main()
