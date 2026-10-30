import { createContext, useContext } from 'react';
import type { Enforcement } from '../api/types';

/**
 * Whether the gateway enforces its decisions or only records them ("shadow", report-only). `undefined` means the
 * backend did not say (older gateway, or config not loaded yet): the UI then assumes nothing and shows no shadow
 * wording.
 */
export const EnforcementContext = createContext<Enforcement | undefined>(undefined);

export const useEnforcement = () => useContext(EnforcementContext);
