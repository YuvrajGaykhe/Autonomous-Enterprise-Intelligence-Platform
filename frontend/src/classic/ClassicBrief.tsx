/** Classic view's brief page (spec §8.1, §8.4–§8.6). */

import { useLocation, useParams } from 'react-router';

import { BriefDetail } from '@/panels/BriefDetail';

export function ClassicBrief() {
  const { briefId = '' } = useParams();
  const { search } = useLocation();
  return (
    <BriefDetail
      key={briefId}
      briefId={briefId}
      inboxHref={{ pathname: '/classic/inbox', search }}
    />
  );
}
