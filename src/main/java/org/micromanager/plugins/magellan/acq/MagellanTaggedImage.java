///////////////////////////////////////////////////////////////////////////////
// AUTHOR:       Henry Pinkard, henry.pinkard@gmail.com
//
// COPYRIGHT:    University of California, San Francisco, 2015
//
// LICENSE:      This file is distributed under the BSD license.
//               License text is included with the source distribution.
//
//               This file is distributed in the hope that it will be useful,
//               but WITHOUT ANY WARRANTY; without even the implied warranty
//               of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
//
//               IN NO EVENT SHALL THE COPYRIGHT OWNER OR
//               CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
//               INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES.
//

package main.java.org.micromanager.plugins.magellan.acq;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import main.java.org.micromanager.plugins.magellan.json.JSONObject;

/**
 *
 * @author Henry
 */
public class MagellanTaggedImage {

   static MagellanTaggedImage createAcquisitionFinishedImage() {
      return new MagellanTaggedImage();
   }
   
   static boolean isAcquisitionFinishedImage(MagellanTaggedImage img) {
      return img.acqFinishedSignal_;
   }
   
   
   public final JSONObject tags;
   public final Object pix;
   private final boolean acqFinishedSignal_;
   
   public MagellanTaggedImage() {
      tags =null;
      pix =null;
      acqFinishedSignal_ = true;
   }
   
   public MagellanTaggedImage(Object pix, JSONObject tags) {
      this.pix = pix;
      this.tags = tags;
      acqFinishedSignal_ = false;
   }
   
  public JSONObject getTags() {
      return tags;
  }
   
  public byte[] get16BitPixelsAsByteArray() {
     short[] shortArray = (short[]) pix;
      ByteBuffer byteBuf = ByteBuffer.allocate(2 * shortArray.length );
      for (int i = 0; i < shortArray.length; i++) {
         byteBuf.putShort(shortArray[i]);
      }
      byteBuf.order(ByteOrder.BIG_ENDIAN);
      return byteBuf.array();
   }

   public boolean is8Bit() {
      return this.pix instanceof byte[];
   }
   
   public byte[] get8BitData() {
      return (byte[]) this.pix;
   }
   
   public short[] get16BitData() {
      return (short[]) this.pix;
   }
   
}
