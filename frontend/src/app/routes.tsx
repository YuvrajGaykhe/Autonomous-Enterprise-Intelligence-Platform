/** The route table (spec §8.1). F2 adds the inbox, brief and agent pages; F3 the office. */

import type { RouteObject } from 'react-router';

import { ClassicHome } from '@/classic/ClassicHome';
import { ClassicLayout } from '@/classic/ClassicLayout';
import { NotFound } from '@/classic/NotFound';

import { AppShell } from './AppShell';
import { HomeRedirect } from './HomeRedirect';
import { RouteError } from './RouteError';

export const routes: RouteObject[] = [
  {
    element: <AppShell />,
    errorElement: <RouteError />,
    children: [
      { path: '/', element: <HomeRedirect /> },
      {
        path: '/classic',
        element: <ClassicLayout />,
        children: [{ index: true, element: <ClassicHome /> }],
      },
      { path: '*', element: <NotFound /> },
    ],
  },
];
