import VirtualList from './VirtualList.jsx';
import DeferredMount from './DeferredMount.jsx';
import CardListSkeleton from './CardListSkeleton.jsx';
import { t } from '../../../strings/index.js';

/**
 * The violation card list of the file and principle detail pages.
 *
 * Both pages get all their data through nav params, so nothing fetches and
 * without the two-commit split the first paint waits for every visible
 * card's pretext layout effect: the click that navigated here looks ignored.
 * Header first, cards one commit later. `resetKey` remounts the list (and
 * its measurements) when the page's item set changes identity.
 */
export default function DeferredViolationList({ resetKey, items, scrollElement, estimateSize, getItemKey, renderItem }) {
  return (
    <DeferredMount fallback={<CardListSkeleton />}>
      <VirtualList
        key={resetKey}
        items={items}
        scrollElement={scrollElement}
        estimateSize={estimateSize}
        getItemKey={getItemKey}
        label={t('explorer.violationsListAria')}
        renderItem={renderItem}
      />
    </DeferredMount>
  );
}
