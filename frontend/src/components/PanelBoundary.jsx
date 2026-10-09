import { Component } from 'react';
import { AlertTriangle } from 'lucide-react';

/**
 * One panel failing must not take the page with it.
 *
 * React unmounts the whole tree when a render throws and nothing catches it.
 * That is how `ProximityView` reading a figure off a payload that legitimately
 * omitted it produced a **completely blank client page** — on the one real
 * client in the dataset. Nothing on screen. No heading, no navigation, no clue.
 *
 * Shashi Bhushan, 21 Sep, on what this demo cannot do:
 *
 *     "No matter where we click, our app should support that... these guys are
 *      engineers, they build things, they break things."
 *
 * The specific bug is fixed at its source. This exists so the next one — and
 * there will be a next one — costs a panel instead of a page.
 *
 * It deliberately does NOT retry or hide. A panel that failed says it failed,
 * names itself, and leaves everything around it usable.
 */
export default class PanelBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { failed: false, message: '' };
  }

  static getDerivedStateFromError(error) {
    return { failed: true, message: String(error?.message || error) };
  }

  componentDidCatch(error, info) {
    // Still log it. A swallowed error is how a panel stays broken for weeks.
    console.error(`[${this.props.name || 'panel'}] render failed`, error, info);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="callout warn">
        <AlertTriangle size={14} />{' '}
        <b>{this.props.name || 'This panel'} could not be shown.</b>{' '}
        The rest of the page is unaffected.
        <div className="small muted u-mt-1">{this.state.message}</div>
      </div>
    );
  }
}
